from __future__ import annotations

from fastapi.testclient import TestClient

from kfxbrain import api


SAMPLE = {
    "pair": "EUR_USD",
    "timeframe": "H1",
    "market": {"price": 1.0862, "spread_pips": 0.8},
    "technicals": {"rsi_14": 57.2, "ema_20": 1.084, "ema_50": 1.081},
}

MARKET_SAMPLE = {
    "timeframe": "H1",
    "pairs": [
        {
            "pair": "EUR_USD",
            "market": {"price": 1.0862, "spread_pips": 0.8},
            "macro": {"rate_differential_pct": 1.4},
            "flows": {"futures_net_change_pct": 2.1},
        },
        {
            "pair": "USD_JPY",
            "market": {"price": 156.42, "spread_pips": 1.0},
            "macro": {"intervention_risk": "elevated"},
            "positioning": {"speculative_net_percentile": 87},
        },
    ],
    "account_context": {"leverage": 25, "margin_level_pct": 420, "stop_out_level_pct": 100},
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


def test_market_intelligence_routes(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    calls = []

    def fake_analyze(task, payload):
        calls.append((task, len(payload.pairs)))
        return {"task": task}

    monkeypatch.setattr(api.brain, "analyze", fake_analyze)
    client = TestClient(api.app)
    routes = {
        "/v1/market/opportunity-ranking": "market_opportunity_ranking",
        "/v1/market/flow-ranking": "market_flow_ranking",
        "/v1/market/anomaly": "market_anomaly",
        "/v1/market/margin-risk": "market_margin_risk",
    }
    for route, task in routes.items():
        response = client.post(route, headers={"X-KFXBrain-Token": "secret"}, json=MARKET_SAMPLE)
        assert response.status_code == 200
        assert response.json()["result"]["task"] == task
    assert calls == [(task, 2) for task in routes.values()]


def test_market_pairs_must_be_unique(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    duplicate = {**MARKET_SAMPLE, "pairs": [MARKET_SAMPLE["pairs"][0]] * 2}
    response = TestClient(api.app).post(
        "/v1/market/opportunity-ranking",
        headers={"X-KFXBrain-Token": "secret"},
        json=duplicate,
    )
    assert response.status_code == 422


def test_pair_signal_requires_matching_pair(monkeypatch):
    monkeypatch.setattr(api.settings, "api_token", "secret")
    monkeypatch.setattr(
        api.brain,
        "analyze",
        lambda task, payload: {"pair": payload.pair, "task": task},
    )
    client = TestClient(api.app)
    response = client.post(
        "/v1/signal/pair/EUR-USD",
        headers={"X-KFXBrain-Token": "secret"},
        json=SAMPLE,
    )
    assert response.status_code == 200
    assert response.json()["result"]["task"] == "pair_signal"

    mismatch = client.post(
        "/v1/signal/pair/USD_JPY",
        headers={"X-KFXBrain-Token": "secret"},
        json=SAMPLE,
    )
    assert mismatch.status_code == 422
