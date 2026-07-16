#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

while IFS=$'\t' read -r directory expected; do
  actual=$(git -C "vendor/$directory" rev-parse HEAD)
  if [[ "$actual" != "$expected" ]]; then
    echo "$directory: expected $expected, found $actual" >&2
    exit 1
  fi
  if [[ -n $(git -C "vendor/$directory" status --short) ]]; then
    echo "$directory: worktree is not clean" >&2
    exit 1
  fi
  echo "$directory $actual OK"
done < <(.venv/bin/python - <<'PY'
import json
from pathlib import Path
for directory, item in json.loads(Path("vendor.lock.json").read_text()).items():
    print(f"{directory}\t{item['commit']}")
PY
)
