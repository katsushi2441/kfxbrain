from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    host: str
    port: int
    api_token: str
    allowed_client_ips: frozenset[str]
    llm_provider: str
    ollama_url: str
    ollama_model: str
    fast_ollama_model: str
    ollama_timeout: int
    deepseek_base_url: str
    deepseek_api_key: str
    deepseek_model: str
    deepseek_timeout: int
    max_input_chars: int

    @property
    def active_model(self) -> str:
        """現在のプロバイダで実際に使うモデル名(表示・レスポンス用)。"""
        if self.llm_provider == "deepseek":
            return self.deepseek_model
        return self.ollama_model


def load_settings() -> Settings:
    allowed = {
        value.strip()
        for value in os.getenv("KFXBRAIN_ALLOWED_CLIENT_IPS", "127.0.0.1,::1,157.7.188.210").split(",")
        if value.strip()
    }
    return Settings(
        host=os.getenv("KFXBRAIN_HOST", "0.0.0.0"),
        port=int(os.getenv("KFXBRAIN_PORT", "18326")),
        api_token=os.getenv("KFXBRAIN_API_TOKEN", "").strip(),
        allowed_client_ips=frozenset(allowed),
        llm_provider=os.getenv("KFXBRAIN_LLM_PROVIDER", "ollama").strip().lower(),
        ollama_url=os.getenv("KFXBRAIN_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.getenv("KFXBRAIN_OLLAMA_MODEL", "gemma4:12b-it-qat").strip(),
        fast_ollama_model=os.getenv("KFXBRAIN_FAST_OLLAMA_MODEL", "gemma4:e4b").strip(),
        ollama_timeout=int(os.getenv("KFXBRAIN_OLLAMA_TIMEOUT", "300")),
        deepseek_base_url=os.getenv("KFXBRAIN_DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        deepseek_api_key=os.getenv("KFXBRAIN_DEEPSEEK_API_KEY", "").strip(),
        deepseek_model=os.getenv("KFXBRAIN_DEEPSEEK_MODEL", "deepseek-v4-flash").strip(),
        deepseek_timeout=int(os.getenv("KFXBRAIN_DEEPSEEK_TIMEOUT", "600")),
        max_input_chars=int(os.getenv("KFXBRAIN_MAX_INPUT_CHARS", "50000")),
    )


settings = load_settings()
