#!/usr/bin/env bash
# Compare thin eval suites (CI-safe). Scores never feed Gate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EVAL_ROOT="${EVAL_ROOT:-$(cd "$ROOT/.." && pwd)/experiment/eval}"
OUT="${EVAL_COMPARE_OUT:-$(mktemp -d /tmp/eglk-eval-compare.XXXXXX)}"
mkdir -p "$OUT"
echo "== eval_compare out=$OUT eval_root=$EVAL_ROOT =="

echo "-- wa_hard batch (prepare + placeholder scores) --"
WA_LIMIT="$(python3 - <<PY
import json
from pathlib import Path
p = Path("$EVAL_ROOT") / "wa_hard" / "pack.json"
n = len((json.loads(p.read_text()).get("tasks") or []) if p.is_file() else [])
print(min(5, n) if n else 0)
PY
)"
if [[ "${WA_LIMIT:-0}" -gt 0 ]]; then
eglk-harness eval --suite wa_hard --batch --limit "$WA_LIMIT" \
  --eval-root "$EVAL_ROOT" \
  --workdir "$OUT/wa_hard" \
  --prepare-only
eglk-harness eval --suite wa_hard --batch --limit "$WA_LIMIT" \
  --eval-root "$EVAL_ROOT" \
  --workdir "$OUT/wa_hard_scored" \
  --external-score "$EVAL_ROOT/wa_hard/fixtures/external_score.example.json" \
  >/dev/null
else
  echo "skip wa_hard batch (no pack)"
fi

echo "-- wa_hard HAR-offline fixture --"
TASK_ID="$(python3 - <<PY
import json
from pathlib import Path
p = Path("$EVAL_ROOT") / "wa_hard" / "pack.json"
tasks = (json.loads(p.read_text()).get("tasks") or []) if p.is_file() else []
print(tasks[0]["id"] if tasks else "")
PY
)"
HAR="$EVAL_ROOT/wa_hard/fixtures/traces/pass_trace.json"
if [[ -n "$TASK_ID" && -f "$HAR" ]]; then
  eglk-harness eval --suite wa_hard --task-id "$TASK_ID" \
    --eval-root "$EVAL_ROOT" \
    --workdir "$OUT/wa_hard_har" \
    --score-har "$HAR" \
    --agent mock --prepare-only
else
  echo "skip har-offline (missing pack task or fixture)"
fi

if [[ -x "$EVAL_ROOT/scripts/run_wa_hard_batch.sh" ]]; then
  echo "-- run_wa_hard_batch (prepare + vendor status) --"
  WA_HARD_OUT="$OUT/wa_hard_batch" WA_HARD_LIMIT=3 \
    bash "$EVAL_ROOT/scripts/run_wa_hard_batch.sh"
fi

echo "-- weave_thin toy-hello prepare+mock --"
if [[ -x "$EVAL_ROOT/scripts/ci_weave_thin.sh" ]]; then
  bash "$EVAL_ROOT/scripts/ci_weave_thin.sh"
else
  eglk-harness eval --suite weave_thin --task-id toy-hello \
    --eval-root "$EVAL_ROOT" \
    --workdir "$OUT/weave" \
    --agent mock --prepare-only
fi

echo "-- weave_lh fixture --"
if [[ -x "$EVAL_ROOT/scripts/run_weave_lh_smoke.sh" ]]; then
  WEAVE_LH_OUT="$OUT/weave_lh" bash "$EVAL_ROOT/scripts/run_weave_lh_smoke.sh"
else
  echo "skip weave_lh smoke script"
fi

echo "-- osworld_aux prepare --"
OS_TASK="$(python3 - <<PY
import json
from pathlib import Path
root = Path("$EVAL_ROOT") / "osworld_aux"
for name in ("pack.json", "pack.example.json"):
    p = root / name
    if not p.is_file():
        continue
    tasks = json.loads(p.read_text()).get("tasks") or []
    if tasks:
        print(tasks[0].get("id") or "")
        break
PY
)"
if [[ -n "$OS_TASK" ]]; then
  eglk-harness eval --suite osworld_aux --task-id "$OS_TASK" \
    --eval-root "$EVAL_ROOT" \
    --workdir "$OUT/osworld" \
    --prepare-only
  if [[ -x "$EVAL_ROOT/scripts/run_osworld_smoke.sh" ]]; then
    OSWORLD_OUT="$OUT/osworld_smoke" bash "$EVAL_ROOT/scripts/run_osworld_smoke.sh" || true
  fi
else
  echo "skip osworld (no pack.example tasks)"
fi

if [[ -x "$EVAL_ROOT/scripts/doctor_eval_env.sh" ]]; then
  echo "-- doctor_eval_env --"
  bash "$EVAL_ROOT/scripts/doctor_eval_env.sh" || true
fi

echo "-- list-tasks smoke --"
eglk-harness eval --suite weave_lh --list-tasks --eval-root "$EVAL_ROOT" >/dev/null
eglk-harness eval --suite wa_hard --list-tasks --eval-root "$EVAL_ROOT" >/dev/null
eglk-harness eval --suite tb21 --list-tasks --eval-root "$EVAL_ROOT" >/dev/null
eglk-harness eval --suite osworld_aux --list-tasks --eval-root "$EVAL_ROOT" >/dev/null

echo "-- tb21 fixture --"
if [[ -x "$EVAL_ROOT/scripts/run_tb21_smoke.sh" ]]; then
  TB21_OUT="$OUT/tb21" bash "$EVAL_ROOT/scripts/run_tb21_smoke.sh"
else
  echo "skip tb21 smoke script"
fi

python3 - <<PY
import json
from pathlib import Path
out = Path("$OUT")
rows = []
wh = out / "wa_hard" / "batch_summary.json"
if wh.is_file():
    s = json.loads(wh.read_text())
    rows.append({"suite": "wa_hard", "count": s.get("count"), "summary": str(wh)})
ws = out / "wa_hard_scored" / "batch_summary.json"
if ws.is_file():
    s = json.loads(ws.read_text())
    rows.append({"suite": "wa_hard_scored", "count": s.get("count"), "summary": str(ws)})
rows.append({"suite": "weave_thin", "status": "ran"})
rows.append({"suite": "weave_lh", "status": "fixture_or_skipped"})
rows.append({"suite": "osworld_aux", "status": "prepared_or_skipped"})
rows.append({"suite": "tb21", "status": "fixture_or_skipped"})
cmp_path = out / "compare_summary.json"
cmp_path.write_text(json.dumps({"note": "scores never Gate; see LH_PARITY.md", "rows": rows}, indent=2) + "\n")
print(cmp_path.read_text())
print("eval_compare: OK")
PY
