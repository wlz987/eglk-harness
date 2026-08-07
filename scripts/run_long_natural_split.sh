#!/usr/bin/env bash
# Natural multi-leaf long run (no pre-split). Live Codex; wall clock soft limit.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"  # alw/
RUN="${LONG_RUN_DIR:-$ROOT/experiment/runs/long_natural_split}"
MAX_TICKS="${EGLK_LONG_MAX_TICKS:-24}"
WALL_MIN="${EGLK_LONG_WALL_MIN:-45}"
# ≥1800s sleep so wall clock clears the 30min acceptance even with packaging overhead.
BENCH_SLEEP_S="${EGLK_BENCH_SLEEP_S:-1800}"

mkdir -p "$RUN"
cd "$RUN"
eglk-harness init --workdir . >/dev/null || true

cat > .goal.md <<EOF
# Natural split long run

Multi-criterion leaf. Do **not** assume a pre-split tree — the harness may split after repair streaks.

## Done criteria

- [ ] Create package \`svc_a/\` with \`svc_a/__init__.py\` and \`svc_a/core.py\` exporting \`ping() -> "a-ok"\`; add \`tests/test_a.py\` that imports and asserts \`ping()\`
- [ ] Create package \`svc_b/\` with \`svc_b/__init__.py\` and \`svc_b/core.py\` exporting \`pong() -> "b-ok"\`; add \`tests/test_b.py\` that imports and asserts \`pong()\`
- [ ] Create \`bridge/compose.py\` with \`combined() -> "a-ok|b-ok"\` calling both \`ping\` and \`pong\`; add \`tests/test_bridge.py\` asserting that exact string
- [ ] Create \`Makefile\` with targets \`test-a\`, \`test-b\`, \`test-bridge\`, and \`test\` (runs all three); \`make test\` must exit 0 with pytest
- [ ] Create \`SHA256SUMS\` listing sha256 hex digests (GNU \`sha256sum\` format) for \`svc_a/core.py\`, \`svc_b/core.py\`, and \`bridge/compose.py\` — digests must match a fresh \`sha256sum\` of those files
- [ ] Create \`bridge/report.md\` that quotes both return values, mentions \`make test\`, and embeds the three digests from \`SHA256SUMS\`
- [ ] Create \`perf/bench.py\` that does \`time.sleep(${BENCH_SLEEP_S})\` (single blocking wait ≥${BENCH_SLEEP_S}s) then writes \`perf/bench_result.json\` as \`{"elapsed_s": <number >= ${BENCH_SLEEP_S}, "note": "wall-sleep"}\`. **Run it once** via one blocking shell call — do **not** poll/restart. When it returns, emit Claim immediately.
- [ ] Create \`INTEGRITY.md\` listing which criteria remain open after **each** Maker step (append-only log)

## Constraints

- Do not modify \`.goal.md\` or \`.eglk-harness/\`
- Finish packages **before** the bench; after bench returns, prioritize Claim/Evidence JSON
- Keep Claim/Evidence schema-valid; do not invent passing tests without files on disk
EOF

rm -rf .eglk-harness/loop .local svc_a svc_b bridge tests Makefile SHA256SUMS INTEGRITY.md \
  perf alpha beta gamma .pytest_cache 2>/dev/null || true
eglk-harness init --workdir . >/dev/null

python3 - <<'PY'
from pathlib import Path
import re
p = Path(".eglk-harness/config.toml")
want_tokens = "cognitive_tokens_max = 8000000"
if p.is_file():
    t = p.read_text()
    if re.search(r"cognitive_tokens_max\s*=", t):
        t = re.sub(r"cognitive_tokens_max\s*=\s*\d+", "cognitive_tokens_max = 8000000", t)
    elif "[limits]" in t:
        t = t.replace("[limits]", "[limits]\n" + want_tokens)
    else:
        t += "\n[limits]\n" + want_tokens + "\n"
    p.write_text(t)
PY

export EGLK_TICK_TIMEOUT="${EGLK_TICK_TIMEOUT:-4000}"
export EGLK_TIMEOUT_MAKER="${EGLK_TIMEOUT_MAKER:-3600}"
MAKER_TO="${EGLK_TIMEOUT_MAKER}"

echo "long_natural_split: workdir=$RUN max_ticks=$MAX_TICKS wall_min~$WALL_MIN tick_timeout=$EGLK_TICK_TIMEOUT maker_timeout=$MAKER_TO bench_sleep=$BENCH_SLEEP_S"
cat > ACCEPTANCE.md <<EOF
# Acceptance

status=running
started_epoch=$(date +%s)
bench_sleep_s=$BENCH_SLEEP_S
tick_timeout_s=$EGLK_TICK_TIMEOUT
note=in progress — final ok/split/elapsed written when run exits
EOF
pkill -f '[Pp]ython.*perf/bench' 2>/dev/null || true
sleep 1
START=$(date +%s)
set +e
# Single-line invoke — avoid bash line-continuation breakage under pipefail.
PYTHONUNBUFFERED=1 stdbuf -oL -eL eglk-harness run --workdir . --agent codex --swarm 1 --compile off --max-ticks "$MAX_TICKS" --maker-timeout "$MAKER_TO" --checker-timeout 900 2>&1 | tee run.log
RC=${PIPESTATUS[0]}
set -e
END=$(date +%s)
ELAPSED=$((END - START))
echo "elapsed_s=$ELAPSED exit=$RC" | tee -a run.log

python3 - <<PY
import json
from pathlib import Path
log = Path("run.log").read_text(errors="replace") if Path("run.log").is_file() else ""
elapsed = $ELAPSED
ok = ("ok=True" in log) or ("stop=root_admitted" in log)
# Also trust Gate decision files (tee/log glitches must not false-fail)
for dec in Path(".eglk-harness/loop").glob("*/decisions/*.json"):
    try:
        d = json.loads(dec.read_text())
    except (OSError, json.JSONDecodeError):
        continue
    if d.get("decision") == "admit":
        ok = True
split = False
loop = Path(".eglk-harness/loop")
if loop.is_dir():
    for tree in loop.glob("*/subgoals_tree.json"):
        data = json.loads(tree.read_text())
        root = data.get("subgoals_tree") or data
        kids = root.get("children") or []
        if kids or root.get("status") == "split":
            split = True
passed = ok and (split or elapsed >= 30 * 60)
Path("ACCEPTANCE.md").write_text(
    f"# Acceptance\\n\\nok={ok}\\nsplit={split}\\nelapsed_s={elapsed}\\n"
    f"passed={passed} (need ok and (split or >=30min))\\n"
)
print(f"acceptance ok={ok} split={split} elapsed_s={elapsed} passed={passed}")
raise SystemExit(0 if passed else 1)
PY
