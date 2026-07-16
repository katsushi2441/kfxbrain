# Vendored OSS sources

Kurage FX Brain vendors and calls the following upstream intelligence implementations.

| Directory | Upstream | Pinned commit | License | Used intelligence |
| --- | --- | --- | --- | --- |
| `vendor/TradingAgents` | `TauricResearch/TradingAgents` | `01477f9afb7a47b849ed4c9259d3a9a4738d9fda` | Apache-2.0 | `TradingAgentsGraph.propagate()` full multi-agent graph |
| `vendor/FinGPT` | `AI4Finance-Foundation/FinGPT` | `3799a0f7a3cb4e8a65686e0f11846632eb57ddf9` | MIT | financial NLP tasks, Forecaster and Financial Report Analysis/RAG task contracts |
| `vendor/ai-hedge-fund` | `virattt/ai-hedge-fund` | `09dd33167bd6b4ea63ae32e7246e70e80632cc81` | MIT | 13 upstream persona prompt builders, news sentiment and portfolio synthesis |

`NautilusTrader`, `QuantConnect Lean`, `Freqtrade`, `FinRL`, and `Qlib` are not vendored here because they do not provide LLM intelligence functions. Broker execution remains outside this project.

The adapters are in `src/kfxbrain/vendor_adapters.py`. Every vendor response includes upstream repository, commit, license, and called feature/function. Vendor failures are returned as visible errors; they never fall back to the old independent prompts.
