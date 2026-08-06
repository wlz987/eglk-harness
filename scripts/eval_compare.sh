#!/usr/bin/env bash
# Compare thin eval suites (CI-safe). Scores never feed Gate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EVAL_ROOT="${EVAL_ROOT:-$(cd "$ROOT/.." && pwd)/experiment/eval}"
OUT="${EVAL_COMPARE_OUT:-$(mktemp -d /tmp/eglk-eval-compare.XXXXXX)}"
mkdir -p "$OUT"
echo "== eval_compare out=$OUT eval_root=$EVAL_ROOT =="

echo "-- wa_hard batch (prepare + placeholder scores) --"
eglk-harness eval --suite wa_hard --batch --limit 5 \
  --eval-root "$EVAL_ROOT" \
  --workdir "$OUT/wa_hard" \
  --prepare-only
# Re-run without prepare-only flag for scores-only path: use prepare_only=false via second call
eglk-harness eval --suite wa_hard --batch --limit 5 \
  --eval-root "$EVAL_ROOT" \
  --workdir "$OUT/wa_hard_scored" \
  --external-score "$EVAL_ROOT/wa_hard/fixtures/external_score.example.json" \
  >/dev/null
# Note: batch with external file applies same fixture path when is_file — ok for smoke

echo "-- weave_thin toy-hello prepare+mock --"
if [[ -x "$EVAL_ROOT/scripts/ci_weave_thin.sh" ]]; then
  bash "$EVAL_ROOT/scripts/ci_weave_thin.sh"
else
  eglk-harness eval --suite weave_thin --task-id toy-hello \
    --eval-root "$EVAL_ROOT" \
    --workdir "$OUT/weave" \
    --agent mock --prepare-only
fi

echo "-- osworld_aux prepare --"
OS_TASK="$(python3 - <<PY
import json
from pathlib import Path
p = Path("$EVAL_ROOT") / "osworld_aux" / "pack.example.json"
if not p.is_file():
    print("")
else:
    data = json.loads(p.read_text())
    tasks = data.get("tasks") or []
    print(tasks[0]["id"] if tasks else "")
PY
)"
if [[ -n "$OS_TASK" ]]; then
  eglk-harness eval --suite osworld_aux --task-id "$OS_TASK" \
    --eval-root "$EVAL_ROOT" \
    --workdir "$OUT/osworld" \
    --prepare-only
else
  echo "skip osworld (no pack.example tasks)"
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
rows.append({"suite": "osworld_aux", "status": "prepared_or_skipped"})
cmp_path = out / "compare_summary.json"
cmp_path.write_text(json.dumps({"note": "scores never Gate", "rows": rows}, indent=2) + "\n")
print(cmp_path.read_text())
print("eval_compare: OK")
PY
