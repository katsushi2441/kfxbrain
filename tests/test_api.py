from __future__ import annotations

from fastapi.testclient import TestClient

from kfxbrain import api


SAMPLE = {
    "pair": "EUR_USD",
    "timeframe": "H1",
    "market": {"price": 1.0862, "spread_pips": 0.8},
    "technicals": {"rsi_14": 57.2, "ema_20": 1.084, "ema_50": 1.081},
}


def test_health(monkeypatch):
    monkeypatch.setattr(api.brain, "health", lambda: {"reachable": True, "model_available": True})
    response = TestClient(api.app).get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_post_requires_token(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    response = TestClient(api.app).post("/v1/analyze/technical", json=SAMPLE)
    assert response.status_code == 401


def test_technical_returns_structured_result(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    monkeypatch.setattr(
        api.brain,
        "analyze",
        lambda task, payload: {"signal": "bullish", "confidence": 0.72, "evidence": ["EMA"]},
    )
    response = TestClient(api.app).post(
        "/v1/analyze/technical",
        headers={"X-KFXBrain-Token": "secret"},
        json=SAMPLE,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "technical"
    assert body["result"]["signal"] == "bullish"


def test_invalid_pair_is_rejected(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    response = TestClient(api.app).post(
        "/v1/analyze/technical",
        headers={"X-KFXBrain-Token": "secret"},
        json={**SAMPLE, "pair": "invalid"},
    )
    assert response.status_code == 422


def test_tradingagents_vendor_route(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    monkeypatch.setattr(api.tradingagents, "run", lambda payload: {"signal": "HOLD"})
    response = TestClient(api.app).post(
        "/v1/vendor/tradingagents/run",
        headers={"X-KFXBrain-Token": "secret"},
        json={"pair": "EUR_USD", "trade_date": "2026-07-15"},
    )
    assert response.status_code == 200
    assert response.json()["result"]["signal"] == "HOLD"


def test_fingpt_vendor_route(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    monkeypatch.setattr(api.fingpt, "run", lambda task, payload: {"feature": task})
    response = TestClient(api.app).post(
        "/v1/vendor/fingpt/sentiment",
        headers={"X-KFXBrain-Token": "secret"},
        json=SAMPLE,
    )
    assert response.status_code == 200
    assert response.json()["result"]["feature"] == "sentiment"


def test_ai_hedge_fund_persona_route(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    monkeypatch.setattr(
        api.ai_hedge_fund,
        "run_persona",
        lambda persona, payload: {"persona": persona},
    )
    response = TestClient(api.app).post(
        "/v1/vendor/ai-hedge-fund/persona/nassim-taleb",
        headers={"X-KFXBrain-Token": "secret"},
        json=SAMPLE,
    )
    assert response.status_code == 200
    assert response.json()["result"]["persona"] == "nassim-taleb"
