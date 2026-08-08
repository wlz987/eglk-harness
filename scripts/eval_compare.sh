#!/usr/bin/env bash
# Eval inventory compare — list-tasks (bundled packs or EGLK_EVAL_ROOT).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EVAL_ROOT="${EVAL_ROOT:-${EGLK_EVAL_ROOT:-}}"
if [[ -z "$EVAL_ROOT" ]]; then
  EVAL_ROOT="$(python3 -c "from eglk_harness.domain.eval.paths import default_eval_root; r=default_eval_root(); print(r or '')")"
fi
if [[ -z "$EVAL_ROOT" || ! -d "$EVAL_ROOT" ]]; then
  echo "skip eval_compare: no eval root (set EGLK_EVAL_ROOT)" >&2
  exit 0
fi
OUT="${EVAL_COMPARE_OUT:-$(mktemp -d /tmp/eglk-eval-compare.XXXXXX)}"
mkdir -p "$OUT"
echo "== eval_compare out=$OUT eval_root=$EVAL_ROOT =="

for suite in weave_lh osworld_aux tb21 wa_hard; do
  echo "-- list-tasks $suite --"
  eglk-harness eval --suite "$suite" --list-tasks --eval-root "$EVAL_ROOT" \
    >"$OUT/list_${suite}.json" || true
done

python3 - <<PY
import json
from pathlib import Path
out = Path("$OUT")
rows = []
for name in ("weave_lh", "osworld_aux", "tb21", "wa_hard"):
    p = out / f"list_{name}.json"
    count = None
    if p.is_file():
        try:
            raw = p.read_text(encoding="utf-8").split("note:", 1)[0].strip()
            count = json.loads(raw).get("count")
        except Exception:
            count = None
    rows.append({"suite": name, "list_count": count})
summary = {"out": str(out), "suites": rows, "note": "inventory only; live runs need EGLK_EVAL_ROOT/vendor"}
(out / "COMPARE_SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
PY
echo "eval_compare: OK"
