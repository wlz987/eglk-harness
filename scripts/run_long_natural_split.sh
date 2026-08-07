#!/usr/bin/env bash
# Natural multi-leaf long run (no pre-split). Live Codex; wall clock soft limit.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"  # alw/
RUN="${LONG_RUN_DIR:-$ROOT/experiment/runs/long_natural_split}"
MAX_TICKS="${EGLK_LONG_MAX_TICKS:-24}"
WALL_MIN="${EGLK_LONG_WALL_MIN:-45}"

mkdir -p "$RUN"
cd "$RUN"
eglk-harness init --workdir . >/dev/null || true
python3 - <<'PY'
from pathlib import Path
p = Path(".eglk-harness/config.toml")
if p.is_file():
    t = p.read_text()
    if "cognitive_tokens_max = 500000" not in t:
        p.write_text(t.replace("# cognitive_tokens_max = 64000", "cognitive_tokens_max = 500000"))
PY

# Multi-criterion leaf — intentionally interlocking so early admit is hard;
# Governor may split after repair streaks. Never pre-split the tree.
cat > .goal.md <<'EOF'
# Natural split long run

Multi-criterion leaf. Do **not** assume a pre-split tree — the harness may split after repair streaks.

## Done criteria

- [ ] Create package `svc_a/` with `svc_a/__init__.py` and `svc_a/core.py` exporting `ping() -> "a-ok"`; add `tests/test_a.py` that imports and asserts `ping()`
- [ ] Create package `svc_b/` with `svc_b/__init__.py` and `svc_b/core.py` exporting `pong() -> "b-ok"`; add `tests/test_b.py` that imports and asserts `pong()`
- [ ] Create `bridge/compose.py` with `combined() -> "a-ok|b-ok"` calling both `ping` and `pong`; add `tests/test_bridge.py` asserting that exact string
- [ ] Create `Makefile` with targets `test-a`, `test-b`, `test-bridge`, and `test` (runs all three); `make test` must exit 0 with pytest
- [ ] Create `SHA256SUMS` listing sha256 hex digests (GNU `sha256sum` format) for `svc_a/core.py`, `svc_b/core.py`, and `bridge/compose.py` — digests must match a fresh `sha256sum` of those files
- [ ] Create `bridge/report.md` that quotes both return values, mentions `make test`, and embeds the three digests from `SHA256SUMS`
- [ ] Create `INTEGRITY.md` listing which criteria remain open after **each** Maker step (append-only log)

## Constraints

- Do not modify `.goal.md` or `.eglk-harness/`
- Prefer finishing one package before expanding; leave inspectable evidence for Checker
- Keep Claim/Evidence schema-valid; do not invent passing tests without files on disk
EOF

rm -rf .eglk-harness/loop .local svc_a svc_b bridge tests Makefile SHA256SUMS INTEGRITY.md \
  alpha beta gamma 2>/dev/null || true
eglk-harness init --workdir . >/dev/null
# re-apply token budget after init
python3 - <<'PY'
from pathlib import Path
p = Path(".eglk-harness/config.toml")
if p.is_file():
    t = p.read_text()
    if "cognitive_tokens_max = 500000" not in t:
        if "cognitive_tokens_max" in t:
            import re
            t = re.sub(r"cognitive_tokens_max\s*=\s*\d+", "cognitive_tokens_max = 500000", t)
        else:
            t += "\n[limits]\ncognitive_tokens_max = 500000\n"
        p.write_text(t)
PY

echo "long_natural_split: workdir=$RUN max_ticks=$MAX_TICKS wall_min~$WALL_MIN"
START=$(date +%s)
set +e
PYTHONUNBUFFERED=1 stdbuf -oL -eL eglk-harness run --workdir . --agent codex --swarm 1 --compile off --max-ticks "$MAX_TICKS" 2>&1 | tee run.log
RC=${PIPESTATUS[0]}
set -e
END=$(date +%s)
ELAPSED=$((END - START))
echo "elapsed_s=$ELAPSED exit=$RC" | tee -a run.log

python3 - <<PY
import json
from pathlib import Path
log = Path("run.log").read_text(errors="replace")
elapsed = $ELAPSED
ok = "ok=True" in log or "stop=root_admitted" in log
split = False
loop = Path(".eglk-harness/loop")
if loop.is_dir():
    for tree in loop.glob("*/subgoals_tree.json"):
        data = json.loads(tree.read_text())
        root = data.get("subgoals_tree") or data
        kids = root.get("children") or []
        if kids:
            split = True
        if root.get("status") == "split":
            split = True
passed = ok and (split or elapsed >= 30 * 60)
Path("ACCEPTANCE.md").write_text(
    f"# Acceptance\\n\\nok={ok}\\nsplit={split}\\nelapsed_s={elapsed}\\n"
    f"passed={passed} (need ok and (split or >=30min))\\n"
)
print(f"acceptance ok={ok} split={split} elapsed_s={elapsed} passed={passed}")
raise SystemExit(0 if passed else 1)
PY
