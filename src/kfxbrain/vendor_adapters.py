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
    "finrobot": {
        "name": "AI4Finance-Foundation/FinRobot",
        "commit": "297a8d28d099be328c8a8eb658b4f782b93f3651",
        "license": "Apache-2.0",
    },
    "finmem": {
        "name": "pipiku915/FinMem-LLM-StockTrading",
        "commit": "be814aa47970de9bf2fdd6a1d5a60ae5cf361b46",
        "license": "MIT",
    },
}


def vendor_status() -> dict[str, Any]:
    folders = {
        "tradingagents": "TradingAgents",
        "fingpt": "FinGPT",
        "ai-hedge-fund": "ai-hedge-fund",
        "finrobot": "FinRobot",
        "finmem": "FinMem",
    }
    return {
        # submoduleは.gitがファイル、単独cloneはディレクトリなのでexists()で判定
        key: {**UPSTREAM[key], "installed": (VENDOR_ROOT / folder / ".git").exists()}
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
                from tradingagents.llm_clients import openai_client as _oc
            except Exception as exc:
                raise BrainError(f"TradingAgents import failed: {exc}") from exc

            # 上流はmax_tokensをLLMへ渡さない(_PASSTHROUGH_KWARGSに無い・_get_provider_kwargsも
            # 温度とretryだけ転送)。そのため各レポートが無制限に長文化し5.5分かかる。vendorは
            # 編集せず、実行時にmax_tokens転送を有効化して出力長を抑え、180秒プロキシ上限に収める。
            if "max_tokens" not in _oc._PASSTHROUGH_KWARGS:
                _oc._PASSTHROUGH_KWARGS = _oc._PASSTHROUGH_KWARGS + ("max_tokens",)
            _orig_kwargs = TradingAgentsGraph._get_provider_kwargs
            if getattr(_orig_kwargs, "_kfxbrain_maxtok", False) is False:
                def _kwargs_with_max_tokens(self):
                    kw = _orig_kwargs(self)
                    mt = self.config.get("max_tokens")
                    if mt not in (None, "", 0):
                        kw["max_tokens"] = int(mt)
                    return kw
                _kwargs_with_max_tokens._kfxbrain_maxtok = True
                TradingAgentsGraph._get_provider_kwargs = _kwargs_with_max_tokens

            config = deepcopy(DEFAULT_CONFIG)
            work = Path(__file__).resolve().parents[2] / "data" / "tradingagents"
            # リバースプロキシの読み取り上限(180秒)に収めるための高速プロファイル
            # (PayApi/Chet 2026-07-18指摘)。5.5分の主因は長文レポート×多数の逐次LLM。
            # 対策: quick-thinkを高速モデル(e4b)に、reasoning系の deep-think だけ12bを維持、
            # 分析役を市場のみ(fast_analysts)に絞り、討論/リスクは各1ラウンド。
            # 深い判断が要る場合は debate_rounds/risk_rounds を上げて呼び出し側で許容する。
            config.update(
                {
                    "llm_provider": "ollama",
                    "deep_think_llm": self.settings.fast_ollama_model,
                    "quick_think_llm": self.settings.fast_ollama_model,
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
                    "max_tokens": 700,
                }
            )
            symbol = request.pair.replace("_", "")
            trade_date = request.trade_date or date.today().isoformat()
            analysts = [a.strip() for a in (request.analysts or ["market"]) if a.strip()]
            try:
                graph = TradingAgentsGraph(
                    selected_analysts=analysts,
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


# FinRobotのAnnual Report Analyzer: 分析指示(dedent文字列)が
# finrobot/functional/analyzer.py の各analyze_*関数内にある。上流moduleの
# importはyfinance/SEC依存を引き込むため、固定コミットのソースからASTで
# 指示テキストだけを抽出して使う(コピーせず、実行時にvendorから読む)。
FINROBOT_SECTIONS = {
    "income_stmt": "analyze_income_stmt",
    "balance_sheet": "analyze_balance_sheet",
    "cash_flow": "analyze_cash_flow",
    "segment_stmt": "analyze_segment_stmt",
    "risk_assessment": "get_risk_assessment",
    "competitors": "get_competitors_analysis",
    "business_highlights": "analyze_business_highlights",
    "company_description": "analyze_company_description",
}


class FinRobotAdapter:
    """FinRobot(AI4Finance)のアナリスト指示とMarket Forecasterワークフローを実行する。"""

    def __init__(self, brain: FxBrain) -> None:
        self.brain = brain
        self._instructions: dict[str, str] | None = None

    def _load_instructions(self) -> dict[str, str]:
        if self._instructions is not None:
            return self._instructions
        import ast

        path = VENDOR_ROOT / "FinRobot" / "finrobot" / "functional" / "analyzer.py"
        if not path.is_file():
            raise BrainError("FinRobot vendor is not installed")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found: dict[str, str] = {}
        wanted = {v: k for k, v in FINROBOT_SECTIONS.items()}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in wanted:
                for sub in ast.walk(node):
                    # instruction = dedent("""...""") の文字列定数を拾う
                    if (isinstance(sub, ast.Assign) and sub.targets
                            and isinstance(sub.targets[0], ast.Name)
                            and sub.targets[0].id == "instruction"):
                        call = sub.value
                        if isinstance(call, ast.Call) and call.args and isinstance(call.args[0], ast.Constant):
                            found[wanted[node.name]] = str(call.args[0].value).strip()
                        elif isinstance(call, ast.Constant):
                            found[wanted[node.name]] = str(call.value).strip()
        missing = set(FINROBOT_SECTIONS) - set(found)
        if missing:
            raise BrainError(f"FinRobot instructions not found for: {sorted(missing)}")
        self._instructions = found
        return found

    def report_section(self, section: str, request: FxBrainRequest) -> dict[str, Any]:
        if section not in FINROBOT_SECTIONS:
            raise BrainError(f"unknown FinRobot section: {section}")
        instruction = self._load_instructions()[section]
        # 上流のcombine_prompt(instruction, resource, table)と同じ結合順
        prompt = (
            f"{request.compact_json()}\n\n"
            f"Resource: the JSON evidence above supplied by the caller\n\n"
            f"Instruction: {instruction}\n"
            "Use only the supplied evidence; state what is missing instead of inventing. Return JSON only. "
            'Schema: {"analysis":"...","key_points":["..."],"missing_data":["..."]}'
        )
        output = self.brain.generate_json(prompt)
        return {
            "vendor": UPSTREAM["finrobot"],
            "function": f"finrobot.functional.analyzer.ReportAnalysisUtils.{FINROBOT_SECTIONS[section]}",
            "section": section,
            "output": output,
        }

    def forecast(self, request: FxBrainRequest) -> dict[str, Any]:
        # FinRobotのMarket Forecasterエージェント(agent_fingpt_forecaster)のタスク契約:
        # ポジティブ材料と懸念を2-4個ずつ、翌週の値動きを%レンジで予測し、根拠を要約する。
        prompt = (
            "You are executing the FinRobot Market Forecaster workflow. "
            f"Analyze the positive developments and potential concerns of {request.pair} "
            "with 2-4 most important factors respectively and keep them concise. "
            "Most factors should be inferred from the supplied news and market data. "
            "Then make a rough prediction (e.g. up/down by 2-3%) of the price movement for next week, "
            "and provide a summary analysis to support your prediction. "
            "Use only the supplied evidence. Return JSON only. Schema: "
            '{"positive_developments":["..."],"potential_concerns":["..."],'
            '"prediction":"up|down x-y%","confidence":0,"summary":"..."}\n'
            f"Evidence: {request.compact_json()}"
        )
        output = self.brain.generate_json(prompt)
        return {
            "vendor": UPSTREAM["finrobot"],
            "function": "finrobot agents workflow: Market_Forecaster (agent_fingpt_forecaster)",
            "output": output,
        }


class FinMemAdapter:
    """FinMem(階層メモリ+性格設計のLLMトレーダー)。上流puppy/prompts.pyの
    プロンプト実体を直接importして使う(依存ゼロの純文字列モジュール)。
    メモリDBは持たず、呼び出し側がprior_reportsで各層の記憶を渡すステートレス設計。"""

    def __init__(self, brain: FxBrain) -> None:
        self.brain = brain
        self._prompts = None

    def _load_prompts(self):
        if self._prompts is None:
            path = VENDOR_ROOT / "FinMem" / "puppy" / "prompts.py"
            if not path.is_file():
                raise BrainError("FinMem vendor is not installed")
            # puppy/__init__.pyはfaiss等の重依存を引くため、prompts.py(依存ゼロの
            # 純文字列モジュール)だけをファイルから直接ロードする
            import importlib.util
            spec = importlib.util.spec_from_file_location("finmem_prompts", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._prompts = module
        return self._prompts

    @staticmethod
    def _memory_block(request: FxBrainRequest) -> str:
        layers = request.prior_reports or {}
        lines = []
        for layer in ("short", "mid", "long", "reflection"):
            items = layers.get(layer) or []
            if isinstance(items, str):
                items = [items]
            for i, item in enumerate(items):
                lines.append(f"[{layer}-term memory id {i}] {item}")
        if request.news:
            for i, item in enumerate(request.news):
                lines.append(f"[short-term memory id news-{i}] {item}")
        return "\n".join(lines) if lines else "(no memories supplied)"

    def decide(self, request: FxBrainRequest) -> dict[str, Any]:
        p = self._load_prompts()
        cum_return = float((request.position or {}).get("cumulative_return", 0) or 0)
        character = "risk-seeking" if cum_return >= 0 else "risk-averse"
        investment_info = (
            p.test_investment_info_prefix.format(symbol=request.pair, cur_date=request.as_of or "today")
            + "\n" + p.test_sentiment_explanation
            + "\n" + p.test_momentum_explanation
            + "\nMemories:\n" + self._memory_block(request)
            + f"\nPosition context: {json.dumps(request.position or {}, ensure_ascii=False)}"
            + f"\nTechnicals: {json.dumps(request.technicals or {}, ensure_ascii=False)}"
        )
        # 上流test_promptの契約(gradio用のJSON suffixは自前スキーマに差替え)
        base = p.test_prompt.split("${gr.complete_json_suffix_v2}")[0]
        prompt = (
            base.replace("${investment_info}", investment_info)
            + f"\nYour character right now is {character} (cumulative return {cum_return}).\n"
            "Return JSON only. Schema: "
            '{"investment_decision":"buy|sell|hold","summary_reason":"...",'
            '"supporting_memory_ids":["..."],"confidence":0}'
        )
        output = self.brain.generate_json(prompt)
        return {
            "vendor": UPSTREAM["finmem"],
            "function": "puppy.prompts.test_prompt (layered-memory decision, character switching)",
            "character": character,
            "output": output,
        }

    def reflect(self, request: FxBrainRequest) -> dict[str, Any]:
        p = self._load_prompts()
        investment_info = (
            f"The ticker analyzed is {request.pair}, current date {request.as_of or 'today'}.\n"
            f"Observed outcome: {json.dumps(request.position or {}, ensure_ascii=False)}\n"
            "Memories:\n" + self._memory_block(request)
        )
        base = p.train_prompt.split("${gr.complete_json_suffix_v2}")[0]
        prompt = (
            base.replace("${investment_info}", investment_info)
            + "\nReturn JSON only. Schema: "
            '{"summary_reason":"...","supporting_memory_ids":["..."],'
            '"lesson_for_future":"..."}'
        )
        output = self.brain.generate_json(prompt)
        return {
            "vendor": UPSTREAM["finmem"],
            "function": "puppy.prompts.train_prompt (reflection loop)",
            "output": output,
        }
