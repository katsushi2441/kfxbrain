#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VENV=${VENV:-"$ROOT/.venv"}

"$VENV/bin/pip" install "$ROOT/vendor/TradingAgents" "finnhub-python>=2.4,<3"
