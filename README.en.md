# Kurage FX Brain

[Japanese README](README.md)

Kurage FX Brain exposes reusable financial intelligence as authenticated HTTP APIs for foreign-exchange systems. It combines Gemma 4 with pinned open-source intelligence workflows while keeping broker credentials, position sizing, and order execution outside the service.

## What It Provides

- Full TradingAgents multi-agent analysis, debate, risk review, final decision, and memory workflow
- FinGPT-inspired financial sentiment, headline classification, relation extraction, named-entity extraction, financial Q&A, forecasting, and report analysis
- Thirteen upstream AI Hedge Fund investor-persona prompt builders
- AI Hedge Fund news sentiment and portfolio synthesis tasks
- Structured JSON responses suitable for agent systems and metered intelligence APIs
- A common-login PHP test console for the Kurage deployment

## Architecture

The project separates the open application body from the LLM intelligence layer:

1. A caller supplies an FX pair and structured evidence.
2. FastAPI authenticates the request and routes it to an intelligence adapter.
3. The adapter invokes a pinned upstream workflow or task contract.
4. Gemma 4 runs locally through Ollama with thinking disabled.
5. The API returns structured analysis only. It never places an order.

The following upstream projects are pinned under `vendor/` as Git submodules:

| Project | License | Integration |
| --- | --- | --- |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Apache-2.0 | Calls `TradingAgentsGraph.propagate()` without patching upstream code |
| [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | MIT | Uses financial NLP, Forecaster, and Financial Report Analysis task contracts |
| [AI Hedge Fund](https://github.com/virattt/ai-hedge-fund) | MIT | Calls upstream `generate_*_output()` persona prompt builders with a local Gemma transport |

Exact revisions are recorded in `vendor.lock.json` and verified by `scripts/verify_vendor.sh`.

## API Groups

### TradingAgents

```text
POST /v1/vendor/tradingagents/run
```

Runs market analysis, sentiment analysis, news analysis, bull/bear debate, research management, trader planning, three-way risk debate, portfolio management, and decision memory as one upstream graph.

### FinGPT Tasks

```text
POST /v1/vendor/fingpt/sentiment
POST /v1/vendor/fingpt/headline
POST /v1/vendor/fingpt/relations
POST /v1/vendor/fingpt/entities
POST /v1/vendor/fingpt/qa
POST /v1/vendor/fingpt/forecast
POST /v1/vendor/fingpt/report
```

### AI Hedge Fund

```text
POST /v1/vendor/ai-hedge-fund/persona/{persona}
POST /v1/vendor/ai-hedge-fund/news-sentiment
POST /v1/vendor/ai-hedge-fund/portfolio
```

Available personas are returned by `GET /v1/meta`. They include Aswath Damodaran, Benjamin Graham, Bill Ackman, Cathie Wood, Charlie Munger, Michael Burry, Mohnish Pabrai, Nassim Taleb, Peter Lynch, Phil Fisher, Rakesh Jhunjhunwala, Stanley Druckenmiller, and Warren Buffett.

The original compact FX endpoints remain available for technical, macro, sentiment, debate, trade, risk, portfolio, review, and combined analysis.

## Requirements

- Python 3.10 or later
- Ollama
- `gemma4:12b-it-qat`

## Setup

Clone with submodules:

```bash
git clone --recurse-submodules https://github.com/katsushi2441/kfxbrain.git
cd kfxbrain
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
scripts/install_vendor.sh
cp .env.sample .env
```

Set a strong `KFXBRAIN_API_TOKEN` in `.env`, then start the service:

```bash
set -a
source .env
set +a
.venv/bin/uvicorn kfxbrain.api:app --host 0.0.0.0 --port 18326
```

## Example

```bash
curl -X POST http://127.0.0.1:18326/v1/vendor/fingpt/sentiment \
  -H "Content-Type: application/json" \
  -H "X-KFXBrain-Token: $KFXBRAIN_API_TOKEN" \
  -d '{
    "pair": "EUR_USD",
    "timeframe": "H1",
    "market": {"price": 1.0862},
    "macro": {"fed": "easing bias"},
    "news": [{"title": "Fed signals possible rate cuts"}]
  }'
```

## Verification

```bash
scripts/verify_vendor.sh
.venv/bin/ruff check src tests
.venv/bin/pytest -q
php -l public/kfxbrain.php
```

## Security And Safety

- Every intelligence POST requires `X-KFXBrain-Token`.
- Client IP restrictions can be configured with `KFXBRAIN_ALLOWED_CLIENT_IPS`.
- The public PHP console keeps the API token on the server and requires common administrator login plus CSRF validation.
- There is no silent model, template, or rule-based fallback.
- The service does not store broker credentials or execute trades.
- Outputs are research artifacts, not investment advice.

## License

The original Kurage FX Brain code is licensed under the MIT License. Vendored submodules retain their respective upstream licenses. See [SOURCES.md](SOURCES.md) for pinned revisions and integration details.
