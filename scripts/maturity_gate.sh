#!/usr/bin/env bash
# Local maturity gate — no live LLM required.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "== pytest =="
pytest -q
echo "== projections =="
eglk-harness check-projections
echo "== soak-bypass mock =="
eglk-harness soak-bypass --agent mock
echo "== weave CI =="
EVAL_ROOT="$(cd "$ROOT/.." && pwd)/experiment/eval"
if [[ -x "$EVAL_ROOT/scripts/ci_weave_thin.sh" ]]; then
  bash "$EVAL_ROOT/scripts/ci_weave_thin.sh"
else
  echo "skip weave (eval root missing): $EVAL_ROOT"
fi
echo "== eval_compare =="
bash "$ROOT/scripts/eval_compare.sh"
echo "== doctor_eval_env (soft) =="
if [[ -x "$EVAL_ROOT/scripts/doctor_eval_env.sh" ]]; then
  bash "$EVAL_ROOT/scripts/doctor_eval_env.sh" || true
else
  echo "skip doctor_eval_env"
fi
echo "maturity-gate: OK"
