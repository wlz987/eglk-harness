#!/usr/bin/env bash
# Full maturity sweep (non-interactive). Does NOT start long_natural_split live.
# Scores never feed Gate. Long ACCEPTANCE is monitored separately.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EVAL="$(cd "$ROOT/../experiment/eval" && pwd)"
cd "$ROOT"
echo "== full_maturity_sweep =="
make release-check
make eval-doctor || true
make eval-smokes
bash "$EVAL/scripts/run_wa_hard_live_attempt.sh"
bash "$EVAL/scripts/run_weave_lh_full.sh"
bash "$EVAL/scripts/run_osworld_full.sh"
make pulse || true
echo "full_maturity_sweep: OK (long_natural_split not auto-started)"
