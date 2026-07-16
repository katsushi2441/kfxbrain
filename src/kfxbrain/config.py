from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    host: str
    port: int
    api_token: str
    allowed_client_ips: frozenset[str]
    ollama_url: str
    ollama_model: str
    ollama_timeout: int
    max_input_chars: int


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
        ollama_url=os.getenv("KFXBRAIN_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.getenv("KFXBRAIN_OLLAMA_MODEL", "gemma4:12b-it-qat").strip(),
        ollama_timeout=int(os.getenv("KFXBRAIN_OLLAMA_TIMEOUT", "300")),
        max_input_chars=int(os.getenv("KFXBRAIN_MAX_INPUT_CHARS", "50000")),
    )


settings = load_settings()
