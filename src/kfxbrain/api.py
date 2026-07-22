from __future__ import annotations

import hmac
import time
import uuid
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import settings
from .ollama import REQUEST_PROVIDER, BrainError, FxBrain, resolve_model
from .schemas import (
    BrainResponse,
    FxBrainRequest,
    FxMarketIntelligenceRequest,
    TradingAgentsRequest,
    normalize_pair,
)
from .vendor_adapters import (
    FINROBOT_SECTIONS,
    PERSONAS,
    AiHedgeFundAdapter,
    FinGptAdapter,
    FinMemAdapter,
    FinRobotAdapter,
    TradingAgentsAdapter,
    vendor_status,
)


class ProviderMiddleware:
    """リクエスト単位のLLMプロバイダをヘッダ X-KFXBrain-Provider から contextvar に載せる。
    課金レール(x402/JPYCゲートウェイ)だけが 'deepseek' を注入する。無指定・不正値はサービス
    既定(config.llm_provider=ローカルGemma)のまま。WEBコンソール/kfxai等の直叩きはヘッダを
    付けないのでGemmaを使う。純粋ASGIミドルウェアなのでset値はrun_in_threadpoolの同期
    エンドポイントまで確実に伝播する(BaseHTTPMiddleware/yield依存のcontextvar問題を回避)。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            prov = ""
            for key, value in scope.get("headers", []):
                if key == b"x-kfxbrain-provider":
                    prov = value.decode("latin-1").strip().lower()
                    break
            REQUEST_PROVIDER.set(prov if prov in ("ollama", "deepseek") else "")
        await self.app(scope, receive, send)


app = FastAPI(
    title="Kurage FX Brain API",
    version=__version__,
    description="Structured judgment APIs for FX systems (local Gemma 4 by default; "
                "paid x402 rails use DeepSeek). No broker execution.",
)
app.add_middleware(ProviderMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
brain = FxBrain(settings)
tradingagents = TradingAgentsAdapter(brain, settings)
ai_hedge_fund = AiHedgeFundAdapter(brain)
fingpt = FinGptAdapter(brain)
finrobot = FinRobotAdapter(brain)
finmem = FinMemAdapter(brain)


@app.middleware("http")
async def restrict_post_clients(request: Request, call_next: Callable):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and settings.allowed_client_ips:
        client_ip = request.client.host if request.client else ""
        if client_ip not in settings.allowed_client_ips and client_ip != "testclient":
            return _error_response(403, "client IP is not allowed")
    return await call_next(request)


def _error_response(status_code: int, detail: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content={"ok": False, "detail": detail})


def require_token(x_kfxbrain_token: str = Header(default="")) -> None:
    if not settings.api_token:
        raise HTTPException(503, "KFXBRAIN_API_TOKEN is not configured")
    if not hmac.compare_digest(x_kfxbrain_token, settings.api_token):
        raise HTTPException(401, "invalid API token")


@app.get("/health")
def health() -> dict:
    status = brain.health()
    return {
        "ok": bool(status.get("reachable") and status.get("model_available")),
        "service": "kfxbrain",
        "version": __version__,
        "model": settings.active_model,
        "ollama": status,
        "vendors": vendor_status(),
    }


@app.get("/v1/meta")
def meta() -> dict:
    return {
        "service": "Kurage FX Brain",
        "model": settings.active_model,
        "execution": False,
        "fallback": False,
        "endpoints": [
            "/v1/analyze/technical",
            "/v1/analyze/macro",
            "/v1/analyze/sentiment",
            "/v1/debate/bull-bear",
            "/v1/decide/trade",
            "/v1/assess/risk",
            "/v1/decide/portfolio",
            "/v1/review/trade",
            "/v1/analyze/full",
            "/v1/market/opportunity-ranking",
            "/v1/market/flow-ranking",
            "/v1/market/anomaly",
            "/v1/market/margin-risk",
            "/v1/signal/pair/{pair}",
            "/v1/vendor/tradingagents/run",
            "/v1/vendor/fingpt/{task}",
            "/v1/vendor/ai-hedge-fund/persona/{persona}",
            "/v1/vendor/ai-hedge-fund/news-sentiment",
            "/v1/vendor/ai-hedge-fund/portfolio",
            "/v1/vendor/finrobot/forecast",
            "/v1/vendor/finrobot/report/{section}",
            "/v1/vendor/finmem/decide",
            "/v1/vendor/finmem/reflect",
        ],
        "fingpt_tasks": ["sentiment", "headline", "relations", "entities", "qa", "forecast", "report"],
        "finrobot_sections": sorted(FINROBOT_SECTIONS),
        "ai_hedge_fund_personas": sorted(PERSONAS),
        "vendors": vendor_status(),
        "notes": {
            "personas": (
                "ai-hedge-fund personas are stock-fundamental prompts applied to FX. "
                "They answer in character and may honestly decline (e.g. Buffett treats "
                "currency pairs as outside his circle of competence). Supply macro/news "
                "evidence and treat outputs as character-flavored second opinions, "
                "not FX signals."
            ),
            "tradingagents_run": (
                "Runs the full upstream multi-agent graph with real yfinance FX data "
                "(USDJPY=X style tickers). Expect minutes of latency per call, not seconds."
            ),
        },
    }


def run(task: str, endpoint: str, payload: FxBrainRequest | FxMarketIntelligenceRequest) -> BrainResponse:
    started = time.monotonic()
    try:
        result = brain.analyze(task, payload)
    except BrainError as exc:
        raise HTTPException(502, str(exc)) from exc
    return BrainResponse(
        endpoint=endpoint,
        request_id=uuid.uuid4().hex[:16],
        model=resolve_model(settings),
        latency_ms=round((time.monotonic() - started) * 1000),
        result=result,
    )


def run_vendor(endpoint: str, operation: Callable[[], dict]) -> BrainResponse:
    started = time.monotonic()
    try:
        result = operation()
    except BrainError as exc:
        raise HTTPException(502, str(exc)) from exc
    return BrainResponse(
        endpoint=endpoint,
        request_id=uuid.uuid4().hex[:16],
        model=resolve_model(settings),
        latency_ms=round((time.monotonic() - started) * 1000),
        result=result,
    )


@app.post("/v1/analyze/technical", response_model=BrainResponse, dependencies=[Depends(require_token)])
def technical(payload: FxBrainRequest):
    return run("technical", "technical", payload)


@app.post("/v1/analyze/macro", response_model=BrainResponse, dependencies=[Depends(require_token)])
def macro(payload: FxBrainRequest):
    return run("macro", "macro", payload)


@app.post("/v1/analyze/sentiment", response_model=BrainResponse, dependencies=[Depends(require_token)])
def sentiment(payload: FxBrainRequest):
    return run("sentiment", "sentiment", payload)


@app.post("/v1/debate/bull-bear", response_model=BrainResponse, dependencies=[Depends(require_token)])
def debate(payload: FxBrainRequest):
    return run("debate", "bull-bear", payload)


@app.post("/v1/decide/trade", response_model=BrainResponse, dependencies=[Depends(require_token)])
def trade(payload: FxBrainRequest):
    return run("trade", "trade", payload)


@app.post("/v1/assess/risk", response_model=BrainResponse, dependencies=[Depends(require_token)])
def risk(payload: FxBrainRequest):
    return run("risk", "risk", payload)


@app.post("/v1/decide/portfolio", response_model=BrainResponse, dependencies=[Depends(require_token)])
def portfolio(payload: FxBrainRequest):
    return run("portfolio", "portfolio", payload)


@app.post("/v1/review/trade", response_model=BrainResponse, dependencies=[Depends(require_token)])
def review(payload: FxBrainRequest):
    return run("review", "review", payload)


@app.post("/v1/analyze/full", response_model=BrainResponse, dependencies=[Depends(require_token)])
def full(payload: FxBrainRequest):
    return run("full", "full", payload)


def protected_market_post(path: str, task: str):
    def endpoint(payload: FxMarketIntelligenceRequest):
        return run(task, path, payload)

    endpoint.__name__ = f"run_{task}"
    app.post(path, response_model=BrainResponse, dependencies=[Depends(require_token)])(endpoint)


for route, task_name in {
    "/v1/market/opportunity-ranking": "market_opportunity_ranking",
    "/v1/market/flow-ranking": "market_flow_ranking",
    "/v1/market/anomaly": "market_anomaly",
    "/v1/market/margin-risk": "market_margin_risk",
}.items():
    protected_market_post(route, task_name)


@app.post(
    "/v1/signal/pair/{pair}",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def pair_signal(pair: str, payload: FxBrainRequest):
    try:
        path_pair = normalize_pair(pair)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if path_pair != payload.pair:
        raise HTTPException(422, "path pair must match payload pair")
    return run("pair_signal", f"/v1/signal/pair/{path_pair}", payload)


@app.post(
    "/v1/vendor/tradingagents/run",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def tradingagents_run(payload: TradingAgentsRequest):
    return run_vendor("vendor/tradingagents/run", lambda: tradingagents.run(payload))


@app.post(
    "/v1/vendor/fingpt/{task}",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def fingpt_run(task: str, payload: FxBrainRequest):
    return run_vendor(f"vendor/fingpt/{task}", lambda: fingpt.run(task, payload))


@app.post(
    "/v1/vendor/ai-hedge-fund/persona/{persona}",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def ai_hedge_fund_persona(persona: str, payload: FxBrainRequest):
    return run_vendor(
        f"vendor/ai-hedge-fund/persona/{persona}",
        lambda: ai_hedge_fund.run_persona(persona, payload),
    )


@app.post(
    "/v1/vendor/ai-hedge-fund/news-sentiment",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def ai_hedge_fund_news(payload: FxBrainRequest):
    return run_vendor(
        "vendor/ai-hedge-fund/news-sentiment",
        lambda: ai_hedge_fund.news_sentiment(payload),
    )


@app.post(
    "/v1/vendor/ai-hedge-fund/portfolio",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def ai_hedge_fund_portfolio(payload: FxBrainRequest):
    return run_vendor(
        "vendor/ai-hedge-fund/portfolio",
        lambda: ai_hedge_fund.portfolio(payload),
    )


@app.post(
    "/v1/vendor/finrobot/forecast",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def finrobot_forecast(payload: FxBrainRequest):
    return run_vendor("vendor/finrobot/forecast", lambda: finrobot.forecast(payload))


@app.post(
    "/v1/vendor/finrobot/report/{section}",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def finrobot_report(section: str, payload: FxBrainRequest):
    return run_vendor(
        f"vendor/finrobot/report/{section}",
        lambda: finrobot.report_section(section, payload),
    )


@app.post(
    "/v1/vendor/finmem/decide",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def finmem_decide(payload: FxBrainRequest):
    return run_vendor("vendor/finmem/decide", lambda: finmem.decide(payload))


@app.post(
    "/v1/vendor/finmem/reflect",
    response_model=BrainResponse,
    dependencies=[Depends(require_token)],
)
def finmem_reflect(payload: FxBrainRequest):
    return run_vendor("vendor/finmem/reflect", lambda: finmem.reflect(payload))
