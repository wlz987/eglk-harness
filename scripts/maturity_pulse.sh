#!/usr/bin/env bash
# Read-only maturity pulse — never mutates runs or Gate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "version: $(python -c 'import eglk_harness; print(eglk_harness.__version__)')"
echo "tests:   $(pytest --collect-only -q 2>/dev/null | tail -1)"
echo "-- doctor (host_tick + eval) --"
eglk-harness doctor 2>/dev/null | rg 'host_tick_timeout|eval_|package|python' || true
echo "-- doctor --json ok --"
eglk-harness doctor --json 2>/dev/null | python -c 'import json,sys; d=json.load(sys.stdin); print("ok=", d.get("ok"), "checks=", len(d.get("checks") or []))' || true
LONG="${EGLK_LONG_RUN:-$ROOT/runs/long_natural_split/ACCEPTANCE.md}"
echo "-- long_natural_split --"
if [[ -f "$LONG" ]]; then
  rg -n '^(ok|split|elapsed|passed|status)=' "$LONG" || cat "$LONG"
else
  echo "(no ACCEPTANCE yet at $LONG)"
fi
echo "pulse: OK (read-only)"
