#!/usr/bin/env bash
# Full local CI gate for eglk-harness (no PyPI upload).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Monorepo: sibling experiment/eval when present.
if [[ -z "${EGLK_EVAL_ROOT:-}" ]]; then
  if [[ -d "$ROOT/../experiment/eval" ]]; then
    export EGLK_EVAL_ROOT="$ROOT/../experiment/eval"
  fi
fi

echo "== eglk-harness CI =="
echo "python: $(python --version 2>&1)"
echo "EGLK_EVAL_ROOT=${EGLK_EVAL_ROOT:-unset}"

python -m pip install -q -e .

python -m eglk_harness.domain.product.check_projections
python -m pytest tests/ -q --tb=short

echo "== CI OK =="
