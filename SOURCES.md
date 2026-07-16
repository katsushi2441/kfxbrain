# Vendored OSS sources

Kurage FX Brain vendors and calls the following upstream intelligence implementations.

| Directory | Upstream | Pinned commit | License | Used intelligence |
| --- | --- | --- | --- | --- |
| `vendor/TradingAgents` | `TauricResearch/TradingAgents` | `01477f9afb7a47b849ed4c9259d3a9a4738d9fda` | Apache-2.0 | `TradingAgentsGraph.propagate()` full multi-agent graph |
| `vendor/FinGPT` | `AI4Finance-Foundation/FinGPT` | `3799a0f7a3cb4e8a65686e0f11846632eb57ddf9` | MIT | financial NLP tasks, Forecaster and Financial Report Analysis/RAG task contracts |
| `vendor/ai-hedge-fund` | `virattt/ai-hedge-fund` | `09dd33167bd6b4ea63ae32e7246e70e80632cc81` | MIT | 13 upstream persona prompt builders, news sentiment and portfolio synthesis |
| `vendor/FinRobot` | `AI4Finance-Foundation/FinRobot` | `297a8d28d099be328c8a8eb658b4f782b93f3651` | Apache-2.0 | Market Forecaster workflow contract, ReportAnalysisUtils analyst instructions (AST-extracted from pinned source at runtime) |
| `vendor/FinMem` | `pipiku915/FinMem-LLM-StockTrading` | `be814aa47970de9bf2fdd6a1d5a60ae5cf361b46` | MIT | `puppy.prompts` layered-memory decision/reflection prompts, risk-seeking/averse character switching |

`NautilusTrader`, `QuantConnect Lean`, `Freqtrade`, `FinRL`, and `Qlib` are not vendored here because they do not provide LLM intelligence functions. Broker execution remains outside this project.

The adapters are in `src/kfxbrain/vendor_adapters.py`. Every vendor response includes upstream repository, commit, license, and called feature/function. Vendor failures are returned as visible errors; they never fall back to the old independent prompts.
