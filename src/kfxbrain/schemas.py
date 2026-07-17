from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


def normalize_pair(value: str) -> str:
    normalized = value.strip().upper().replace("/", "_").replace("-", "_")
    if not re.fullmatch(r"[A-Z0-9]{2,10}_[A-Z0-9]{2,10}", normalized):
        raise ValueError("pair must look like EUR_USD or USD_JPY")
    return normalized


class FxBrainRequest(BaseModel):
    pair: str = Field(min_length=3, max_length=20, examples=["EUR_USD"])
    timeframe: str = Field(default="H1", min_length=1, max_length=12)
    as_of: str = Field(default="", max_length=40)
    market: dict[str, Any] = Field(default_factory=dict)
    technicals: dict[str, Any] = Field(default_factory=dict)
    macro: dict[str, Any] = Field(default_factory=dict)
    news: list[Any] = Field(default_factory=list, max_length=40)
    position: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    prior_reports: dict[str, Any] = Field(default_factory=dict)
    question: str = Field(default="", max_length=2000)

    @field_validator("pair")
    @classmethod
    def validate_pair(cls, value: str) -> str:
        return normalize_pair(value)

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[SMHDW]\d{1,3}|[MHDW]\d{1,3}", normalized):
            raise ValueError("timeframe must look like M15, H1 or D1")
        return normalized

    @model_validator(mode="after")
    def require_evidence(self) -> "FxBrainRequest":
        if not any((self.market, self.technicals, self.macro, self.news, self.position, self.history, self.prior_reports)):
            raise ValueError("at least one evidence field is required")
        return self

    def compact_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False, separators=(",", ":"), default=str)


class FxPairEvidence(BaseModel):
    pair: str = Field(min_length=3, max_length=20)
    market: dict[str, Any] = Field(default_factory=dict)
    technicals: dict[str, Any] = Field(default_factory=dict)
    macro: dict[str, Any] = Field(default_factory=dict)
    flows: dict[str, Any] = Field(default_factory=dict)
    positioning: dict[str, Any] = Field(default_factory=dict)
    news: list[Any] = Field(default_factory=list, max_length=20)

    @field_validator("pair")
    @classmethod
    def validate_pair(cls, value: str) -> str:
        return normalize_pair(value)

    @model_validator(mode="after")
    def require_evidence(self) -> "FxPairEvidence":
        if not any((self.market, self.technicals, self.macro, self.flows, self.positioning, self.news)):
            raise ValueError("each pair requires at least one evidence field")
        return self


class FxMarketIntelligenceRequest(BaseModel):
    timeframe: str = Field(default="H1", min_length=1, max_length=12)
    as_of: str = Field(default="", max_length=40)
    pairs: list[FxPairEvidence] = Field(min_length=1, max_length=40)
    global_context: dict[str, Any] = Field(default_factory=dict)
    account_context: dict[str, Any] = Field(default_factory=dict)
    question: str = Field(default="", max_length=2000)

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        return FxBrainRequest.validate_timeframe(value)

    @model_validator(mode="after")
    def require_unique_pairs(self) -> "FxMarketIntelligenceRequest":
        pairs = [item.pair for item in self.pairs]
        if len(pairs) != len(set(pairs)):
            raise ValueError("pairs must contain unique values")
        return self

    def compact_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False, separators=(",", ":"), default=str)


class BrainResponse(BaseModel):
    ok: bool = True
    endpoint: str
    request_id: str
    model: str
    latency_ms: int
    result: dict[str, Any]


class TradingAgentsRequest(BaseModel):
    pair: str = Field(examples=["EUR_USD"])
    trade_date: str = Field(default="", max_length=10)
    debate_rounds: int = Field(default=1, ge=1, le=3)
    risk_rounds: int = Field(default=1, ge=1, le=3)
    analysts: list[str] = Field(default_factory=lambda: ["market"], max_length=4)
    output_language: str = Field(default="Japanese", max_length=40)

    @field_validator("pair")
    @classmethod
    def validate_pair(cls, value: str) -> str:
        normalized = value.strip().upper().replace("/", "_").replace("-", "_")
        if not re.fullmatch(r"[A-Z]{3}_[A-Z]{3}", normalized):
            raise ValueError("pair must look like EUR_USD or USD_JPY")
        return normalized

    @field_validator("trade_date")
    @classmethod
    def validate_trade_date(cls, value: str) -> str:
        value = value.strip()
        if value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("trade_date must use YYYY-MM-DD")
        return value
