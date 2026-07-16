from __future__ import annotations

import json
import re
import threading
from typing import Any

import requests

from .config import Settings, settings
from .prompts import build_prompt
from .schemas import FxBrainRequest


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
}


def extract_json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value).strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(value[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
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

    def health(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.config.ollama_url}/api/tags", timeout=4)
            response.raise_for_status()
            names = {str(item.get("name") or "") for item in response.json().get("models", [])}
            return {"reachable": True, "model_available": self.config.ollama_model in names, "models": sorted(names)}
        except Exception as exc:
            return {"reachable": False, "model_available": False, "error": str(exc)[:200]}

    def analyze(self, task: str, request: FxBrainRequest) -> dict[str, Any]:
        evidence = request.compact_json()
        return validate_result(task, self.generate_json(build_prompt(task, evidence)))

    def generate_json(self, prompt: str, max_tokens: int = 2200) -> dict[str, Any]:
        if len(prompt) > self.config.max_input_chars:
            raise BrainError(f"input exceeds {self.config.max_input_chars} characters")
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
