from __future__ import annotations

import json
import re
import threading
from typing import Any

import requests

from .config import Settings, settings
from .prompts import build_prompt
from .schemas import FxBrainRequest, FxMarketIntelligenceRequest


class BrainError(RuntimeError):
    pass


REQUIRED_RESULT_KEYS = {
    "technical": {"signal", "confidence", "evidence"},
    "macro": {"bias", "confidence", "drivers"},
    "sentiment": {"sentiment", "pair_impact", "confidence"},
    "debate": {"bull_case", "bear_case", "balance"},
    "trade": {"action", "confidence", "invalidation", "rationale"},
    "risk": {"verdict", "risk_score", "hazards", "safeguards"},
    "portfolio": {"action", "confidence", "rationale"},
    "review": {"process_quality", "classification", "lesson", "next_rule"},
    "full": {"technical", "macro", "sentiment", "debate", "trade", "risk"},
    "market_opportunity_ranking": {"ranking"},
    "market_flow_ranking": {"ranking"},
    "market_anomaly": {"anomalies"},
    "market_margin_risk": {"ranking"},
    "pair_signal": {"pair", "direction", "action", "confidence"},
}


def remove_empty_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: remove_empty_keys(item)
            for key, item in value.items()
            if str(key).strip()
        }
    if isinstance(value, list):
        return [remove_empty_keys(item) for item in value]
    return value


def extract_json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value).strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return remove_empty_keys(parsed)
    except json.JSONDecodeError:
        pass
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(value[start : end + 1])
            if isinstance(parsed, dict):
                return remove_empty_keys(parsed)
        except json.JSONDecodeError:
            pass
    raise BrainError("Gemma returned an invalid JSON object")


def validate_result(task: str, result: dict[str, Any]) -> dict[str, Any]:
    missing = REQUIRED_RESULT_KEYS[task] - set(result)
    if missing:
        raise BrainError(f"Gemma result is missing required fields: {', '.join(sorted(missing))}")
    return result


class FxBrain:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self._lock = threading.Lock()

    @property
    def provider(self) -> str:
        return self.config.llm_provider

    @property
    def model(self) -> str:
        return self.config.active_model

    def health(self) -> dict[str, Any]:
        if self.config.llm_provider == "deepseek":
            return self._deepseek_health()
        if self.config.llm_provider != "ollama":
            return {"provider": self.config.llm_provider, "reachable": False,
                    "model_available": False, "error": "KFXBRAIN_LLM_PROVIDER must be ollama or deepseek"}
        try:
            response = requests.get(f"{self.config.ollama_url}/api/tags", timeout=4)
            response.raise_for_status()
            names = {str(item.get("name") or "") for item in response.json().get("models", [])}
            return {"provider": "ollama", "reachable": True,
                    "model_available": self.config.ollama_model in names, "models": sorted(names)}
        except Exception as exc:
            return {"provider": "ollama", "reachable": False, "model_available": False, "error": str(exc)[:200]}

    def _deepseek_headers(self) -> dict[str, str]:
        if not self.config.deepseek_api_key:
            raise BrainError("KFXBRAIN_DEEPSEEK_API_KEY is not configured")
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.config.deepseek_api_key}",
            "Content-Type": "application/json",
        }

    def _deepseek_health(self) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{self.config.deepseek_base_url}/models",
                headers=self._deepseek_headers(),
                timeout=min(self.config.deepseek_timeout, 10),
            )
            response.raise_for_status()
            names = {str(item.get("id") or "") for item in response.json().get("data", [])}
            return {"provider": "deepseek", "reachable": True,
                    "model_available": self.config.deepseek_model in names, "models": sorted(names)}
        except Exception as exc:
            return {"provider": "deepseek", "reachable": False, "model_available": False, "error": str(exc)[:200]}

    def _generate_json_deepseek(self, prompt: str, max_tokens: int) -> dict[str, Any]:
        payload = {
            "model": self.config.deepseek_model,
            "messages": [
                {"role": "system", "content": "Return exactly one valid JSON object and no commentary or markdown."},
                {"role": "user", "content": prompt},
            ],
            "thinking": {"type": "disabled"},
            "stream": False,
            "temperature": 0.15,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            response = requests.post(
                f"{self.config.deepseek_base_url}/chat/completions",
                headers=self._deepseek_headers(),
                json=payload,
                timeout=self.config.deepseek_timeout,
            )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise BrainError(f"DeepSeek request failed: {exc}") from exc
        choices = body.get("choices") or []
        content = str(((choices[0] if choices else {}).get("message") or {}).get("content") or "").strip()
        if not content:
            finish = str((choices[0] if choices else {}).get("finish_reason") or "unknown")
            raise BrainError(f"DeepSeek returned an empty response (finish_reason={finish})")
        return extract_json_object(content)

    def analyze(self, task: str, request: FxBrainRequest | FxMarketIntelligenceRequest) -> dict[str, Any]:
        evidence = request.compact_json()
        return validate_result(task, self.generate_json(build_prompt(task, evidence)))

    def generate_json(self, prompt: str, max_tokens: int = 2200) -> dict[str, Any]:
        if len(prompt) > self.config.max_input_chars:
            raise BrainError(f"input exceeds {self.config.max_input_chars} characters")
        if self.config.llm_provider == "deepseek":
            return self._generate_json_deepseek(prompt, max_tokens)
        if self.config.llm_provider != "ollama":
            raise BrainError("KFXBRAIN_LLM_PROVIDER must be ollama or deepseek")
        payload = {
            "model": self.config.ollama_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": "json",
            "options": {"temperature": 0.15, "num_predict": max_tokens},
        }
        try:
            with self._lock:
                response = requests.post(
                    f"{self.config.ollama_url}/api/generate",
                    json=payload,
                    timeout=self.config.ollama_timeout,
                )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise BrainError(f"Ollama request failed: {exc}") from exc
        raw = str(body.get("response") or "").strip()
        if not raw:
            reason = str(body.get("done_reason") or "unknown")
            raise BrainError(f"Gemma returned an empty response (done_reason={reason})")
        return extract_json_object(raw)
