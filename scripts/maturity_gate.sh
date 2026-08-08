#!/usr/bin/env bash
# Local maturity gate — pytest + projections + soak mock + eval inventory.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "== pytest =="
pytest -q
echo "== projections =="
eglk-harness check-projections
echo "== soak-bypass mock =="
eglk-harness soak-bypass --agent mock
echo "== eval_compare =="
bash "$ROOT/scripts/eval_compare.sh"
echo "maturity-gate: OK"
