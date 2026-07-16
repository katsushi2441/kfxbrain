from __future__ import annotations

import importlib
import json
import sys
import threading
import types
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from .config import Settings
from .ollama import BrainError, FxBrain
from .schemas import FxBrainRequest, TradingAgentsRequest


VENDOR_ROOT = Path(__file__).resolve().parents[2] / "vendor"
UPSTREAM = {
    "tradingagents": {
        "name": "TauricResearch/TradingAgents",
        "commit": "01477f9afb7a47b849ed4c9259d3a9a4738d9fda",
        "license": "Apache-2.0",
    },
    "fingpt": {
        "name": "AI4Finance-Foundation/FinGPT",
        "commit": "3799a0f7a3cb4e8a65686e0f11846632eb57ddf9",
        "license": "MIT",
    },
    "ai-hedge-fund": {
        "name": "virattt/ai-hedge-fund",
        "commit": "09dd33167bd6b4ea63ae32e7246e70e80632cc81",
        "license": "MIT",
    },
}


def vendor_status() -> dict[str, Any]:
    folders = {
        "tradingagents": "TradingAgents",
        "fingpt": "FinGPT",
        "ai-hedge-fund": "ai-hedge-fund",
    }
    return {
        key: {**UPSTREAM[key], "installed": (VENDOR_ROOT / folder / ".git").is_dir()}
        for key, folder in folders.items()
    }


def _prompt_text(prompt: Any) -> str:
    messages = prompt.to_messages() if hasattr(prompt, "to_messages") else prompt
    if not isinstance(messages, list):
        return str(messages)
    rendered = []
    for message in messages:
        role = getattr(message, "type", message.__class__.__name__)
        content = getattr(message, "content", str(message))
        rendered.append(f"[{role}]\n{content}")
    return "\n\n".join(rendered)


class TradingAgentsAdapter:
    """Patchless adapter around TradingAgentsGraph.propagate()."""

    def __init__(self, brain: FxBrain, settings: Settings) -> None:
        self.brain = brain
        self.settings = settings
        self._lock = threading.Lock()

    def run(self, request: TradingAgentsRequest) -> dict[str, Any]:
        root = VENDOR_ROOT / "TradingAgents"
        if not root.is_dir():
            raise BrainError("TradingAgents vendor is not installed")
        with self._lock:
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            try:
                from tradingagents.default_config import DEFAULT_CONFIG
                from tradingagents.graph.trading_graph import TradingAgentsGraph
            except Exception as exc:
                raise BrainError(f"TradingAgents import failed: {exc}") from exc

            config = deepcopy(DEFAULT_CONFIG)
            work = Path(__file__).resolve().parents[2] / "data" / "tradingagents"
            config.update(
                {
                    "llm_provider": "ollama",
                    "deep_think_llm": self.settings.ollama_model,
                    "quick_think_llm": self.settings.ollama_model,
                    "backend_url": f"{self.settings.ollama_url}/v1",
                    "output_language": request.output_language,
                    "max_debate_rounds": request.debate_rounds,
                    "max_risk_discuss_rounds": request.risk_rounds,
                    "results_dir": str(work / "results"),
                    "data_cache_dir": str(work / "cache"),
                    "memory_log_path": str(work / "memory" / "trading_memory.md"),
                    "checkpoint_enabled": True,
                    "temperature": 0.1,
                    "llm_max_retries": 1,
                    "benchmark_ticker": "DX-Y.NYB",
                }
            )
            symbol = request.pair.replace("_", "")
            trade_date = request.trade_date or date.today().isoformat()
            try:
                graph = TradingAgentsGraph(
                    selected_analysts=["market", "social", "news"],
                    debug=False,
                    config=config,
                )
                state, signal = graph.propagate(symbol, trade_date, asset_type="stock")
            except Exception as exc:
                raise BrainError(f"TradingAgents execution failed: {exc}") from exc

        fields = (
            "market_report",
            "sentiment_report",
            "news_report",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
        )
        return {
            "vendor": UPSTREAM["tradingagents"],
            "function": "TradingAgentsGraph.propagate",
            "symbol": symbol,
            "trade_date": trade_date,
            "signal": signal,
            "reports": {field: state.get(field, "") for field in fields},
            "debates": {
                "investment": state.get("investment_debate_state", {}),
                "risk": state.get("risk_debate_state", {}),
            },
        }


PERSONAS = {
    "aswath-damodaran": ("aswath_damodaran", "generate_damodaran_output", {}),
    "ben-graham": ("ben_graham", "generate_graham_output", {}),
    "bill-ackman": ("bill_ackman", "generate_ackman_output", {}),
    "cathie-wood": ("cathie_wood", "generate_cathie_wood_output", {}),
    "charlie-munger": ("charlie_munger", "generate_munger_output", {"confidence_hint": 50}),
    "michael-burry": ("michael_burry", "_generate_burry_output", {}),
    "mohnish-pabrai": ("mohnish_pabrai", "generate_pabrai_output", {}),
    "nassim-taleb": ("nassim_taleb", "generate_taleb_output", {}),
    "peter-lynch": ("peter_lynch", "generate_lynch_output", {}),
    "phil-fisher": ("phil_fisher", "generate_fisher_output", {}),
    "rakesh-jhunjhunwala": ("rakesh_jhunjhunwala", "generate_jhunjhunwala_output", {}),
    "stanley-druckenmiller": ("stanley_druckenmiller", "generate_druckenmiller_output", {}),
    "warren-buffett": ("warren_buffett", "generate_buffett_output", {}),
}


class AiHedgeFundAdapter:
    """Calls upstream persona prompt builders while replacing only the LLM transport."""

    def __init__(self, brain: FxBrain) -> None:
        self.brain = brain
        self._lock = threading.Lock()

    def run_persona(self, persona: str, request: FxBrainRequest) -> dict[str, Any]:
        if persona not in PERSONAS:
            raise BrainError(f"unknown ai-hedge-fund persona: {persona}")
        root = VENDOR_ROOT / "ai-hedge-fund"
        if not root.is_dir():
            raise BrainError("ai-hedge-fund vendor is not installed")
        module_name, function_name, extra = PERSONAS[persona]
        with self._lock:
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            try:
                # Upstream imports every optional cloud provider from its LLM
                # transport. The persona functions only need call_llm, which is
                # deliberately replaced below with the local Gemma transport.
                importlib.import_module("src.utils")
                if "src.utils.llm" not in sys.modules:
                    transport = types.ModuleType("src.utils.llm")

                    def unavailable_transport(*_args, **_kwargs):
                        raise RuntimeError("vendor LLM transport was not connected")

                    transport.call_llm = unavailable_transport
                    sys.modules["src.utils.llm"] = transport
                module = importlib.import_module(f"src.agents.{module_name}")
                function = getattr(module, function_name)
            except Exception as exc:
                raise BrainError(f"ai-hedge-fund import failed: {exc}") from exc

            original_call = module.call_llm

            def local_call_llm(prompt, pydantic_model, **_kwargs):
                schema = pydantic_model.model_json_schema()
                text = (
                    f"{_prompt_text(prompt)}\n\n"
                    "Return one JSON object only. Follow this JSON schema exactly:\n"
                    f"{json.dumps(schema, ensure_ascii=False)}"
                )
                return pydantic_model.model_validate(self.brain.generate_json(text))

            module.call_llm = local_call_llm
            try:
                output = function(
                    ticker=request.pair,
                    analysis_data=request.model_dump(),
                    state={},
                    agent_id=f"{persona}_agent",
                    **extra,
                )
            except Exception as exc:
                raise BrainError(f"ai-hedge-fund {persona} failed: {exc}") from exc
            finally:
                module.call_llm = original_call

        return {
            "vendor": UPSTREAM["ai-hedge-fund"],
            "function": f"src.agents.{module_name}.{function_name}",
            "persona": persona,
            "output": output.model_dump(),
        }

    def news_sentiment(self, request: FxBrainRequest) -> dict[str, Any]:
        prompt = (
            "You are using the ai-hedge-fund news_sentiment_agent classification task. "
            f"Analyze each supplied headline for {request.pair}. Classify impact as positive, negative, or neutral, "
            "then aggregate a bullish, bearish, or neutral signal. Do not invent articles. Return JSON only.\n"
            f"Evidence: {request.compact_json()}\n"
            'Schema: {"articles":[{"headline":"...","sentiment":"positive|negative|neutral",'
            '"confidence":0}],"signal":"bullish|bearish|neutral","confidence":0,"reasoning":"..."}'
        )
        output = self.brain.generate_json(prompt)
        return {
            "vendor": UPSTREAM["ai-hedge-fund"],
            "function": "src.agents.news_sentiment.news_sentiment_agent",
            "output": output,
        }

    def portfolio(self, request: FxBrainRequest) -> dict[str, Any]:
        prompt = (
            "You are using the ai-hedge-fund portfolio manager intelligence. Synthesize the supplied analyst "
            "signals for an FX pair. Choose only buy, sell, or hold; do not choose quantity and do not execute. "
            "Respect all supplied risk constraints. Return JSON only.\n"
            f"Evidence: {request.compact_json()}\n"
            'Schema: {"action":"buy|sell|hold","confidence":0,"reasoning":"...",'
            '"signals_used":["..."],"constraints":["..."]}'
        )
        output = self.brain.generate_json(prompt)
        return {
            "vendor": UPSTREAM["ai-hedge-fund"],
            "function": "src.agents.portfolio_manager.generate_trading_decision (FX-safe adaptation)",
            "output": output,
        }


FINGPT_TASKS = {
    "sentiment": (
        "Financial Sentiment Analysis",
        'Classify the financial impact as negative, neutral, or positive. Schema: '
        '{"sentiment":"negative|neutral|positive","confidence":0,"rationale":"..."}',
    ),
    "headline": (
        "Financial Headline Classification",
        'Determine whether the supplied headlines imply price up, down, or unclear. Schema: '
        '{"direction":"up|down|unclear","confidence":0,"evidence":["..."]}',
    ),
    "relations": (
        "Financial Relation Extraction",
        'Extract financial entity relationships without invention. Schema: '
        '{"relations":[{"source":"...","relation":"...","target":"..."}]}',
    ),
    "entities": (
        "Financial Named-Entity Recognition",
        'Extract people, organizations, locations, currencies, central banks and instruments. Schema: '
        '{"entities":[{"text":"...","type":"..."}]}',
    ),
    "qa": (
        "Financial Q&A",
        'Answer the question only from supplied evidence. Schema: '
        '{"answer":"...","evidence":["..."],"limitations":["..."]}',
    ),
    "forecast": (
        "FinGPT-Forecaster",
        'Analyze 2-4 positive developments and concerns, then predict direction. Schema: '
        '{"positive_developments":["..."],"concerns":["..."],"direction":"up|down|unclear",'
        '"confidence":0,"analysis":"..."}',
    ),
    "report": (
        "Financial Report Analysis/RAG",
        'Summarize and analyze the supplied financial or macro report. Schema: '
        '{"summary":"...","strengths":["..."],"risks":["..."],"outlook":"...",'
        '"questions":["..."]}',
    ),
}


class FinGptAdapter:
    def __init__(self, brain: FxBrain) -> None:
        self.brain = brain

    def run(self, task: str, request: FxBrainRequest) -> dict[str, Any]:
        if task not in FINGPT_TASKS:
            raise BrainError(f"unknown FinGPT task: {task}")
        feature, instruction = FINGPT_TASKS[task]
        prompt = (
            f"You are executing the FinGPT task: {feature}. {instruction}\n"
            "Use only the supplied evidence. State uncertainty. Confidence is 0-100. Return JSON only.\n"
            f"Evidence: {request.compact_json()}"
        )
        output = self.brain.generate_json(prompt)
        source = {
            "forecast": "fingpt/FinGPT_Forecaster",
            "report": "fingpt/FinGPT_FinancialReportAnalysis",
        }.get(task, "FinGPT multi-task financial LLM instructions")
        return {
            "vendor": UPSTREAM["fingpt"],
            "feature": feature,
            "source": source,
            "output": output,
        }
