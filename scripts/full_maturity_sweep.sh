#!/usr/bin/env bash
# CI-safe maturity sweep (no live LLM / no external benchmark matrix).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "== full_maturity_sweep =="
make release-check
bash scripts/eval_compare.sh
make pulse || true
echo "full_maturity_sweep: OK (live long runs are manual: scripts/run_long_natural_split.sh)"
