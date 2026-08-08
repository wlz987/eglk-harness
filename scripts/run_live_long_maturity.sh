#!/usr/bin/env bash
# Live long-horizon maturity lane (:28000).
set -euo pipefail
HARNESS="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${LIVE_LONG_OUT:-$HARNESS/runs/live_long_maturity}"
LOG="$OUT/logs"
mkdir -p "$OUT" "$LOG"
TS="$(date -Is)"

export EGLK_MODEL="${EGLK_MODEL:-Qwen3.6-35B-A3B-AWQ-4bit}"
export EGLK_BASE_URL="${EGLK_BASE_URL:-http://127.0.0.1:28000/v1}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-$EGLK_BASE_URL}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-sk-local-vllm}"
export EGLK_WIRE_API="${EGLK_WIRE_API:-responses}"
export EGLK_COGNITIVE_TOKENS_MAX="${EGLK_COGNITIVE_TOKENS_MAX:-8000000}"
export EGLK_MCP_DISABLE="${EGLK_MCP_DISABLE:-1}"
export EGLK_TICK_TIMEOUT="${EGLK_LIVE_TICK_TIMEOUT:-${EGLK_TICK_TIMEOUT:-4000}}"
export EGLK_TIMEOUT_MAKER="${EGLK_LIVE_TIMEOUT_MAKER:-${EGLK_TIMEOUT_MAKER:-3600}}"
export EGLK_TIMEOUT_CHECKER="${EGLK_LIVE_TIMEOUT_CHECKER:-${EGLK_TIMEOUT_CHECKER:-900}}"
if [[ "${EGLK_TIMEOUT_MAKER}" -lt 1800 ]]; then
  export EGLK_TIMEOUT_MAKER=3600
fi
if [[ "${EGLK_TICK_TIMEOUT}" -lt 2000 ]]; then
  export EGLK_TICK_TIMEOUT=4000
fi
export EGLK_BENCH_SLEEP_S="${EGLK_BENCH_SLEEP_S:-2400}"
export EGLK_LONG_MAX_TICKS="${EGLK_LONG_MAX_TICKS:-28}"
export EGLK_LONG_WALL_MIN="${EGLK_LONG_WALL_MIN:-55}"

{
  echo "# live_long_maturity $TS"
  echo "model=$EGLK_MODEL base=$EGLK_BASE_URL"
  echo "bench_sleep_s=$EGLK_BENCH_SLEEP_S wall_min~$EGLK_LONG_WALL_MIN"
} | tee "$OUT/LAUNCH.md"

if ! curl -sS -m 5 "$EGLK_BASE_URL/models" >/dev/null; then
  echo "FATAL: cannot reach $EGLK_BASE_URL/models" | tee -a "$OUT/LAUNCH.md"
  exit 1
fi

LONG_DIR="${LONG_RUN_DIR:-$OUT/long_natural}"
export LONG_RUN_DIR="$LONG_DIR"
echo "== long_natural → $LONG_DIR ==" | tee -a "$OUT/LAUNCH.md"
set +e
bash "$HARNESS/scripts/run_long_natural_split.sh" >"$LOG/long.out" 2>&1
LONG_RC=$?
set -e
cp -f "$LONG_DIR/ACCEPTANCE.md" "$OUT/LONG_ACCEPTANCE.md" 2>/dev/null || true
echo "long_rc=$LONG_RC" | tee -a "$OUT/LAUNCH.md"

SOAK_DIR="$OUT/soak"
mkdir -p "$SOAK_DIR"
echo "== soak-bypass --live → $SOAK_DIR ==" | tee -a "$OUT/LAUNCH.md"
set +e
eglk-harness soak-bypass --workdir "$SOAK_DIR" --agent codex --live --timeout "${EGLK_SOAK_TIMEOUT:-300}" \
  >"$LOG/soak.out" 2>&1
SOAK_RC=$?
set -e
echo "soak_rc=$SOAK_RC" | tee -a "$OUT/LAUNCH.md"

python3 - <<PY
import json, re, time
from pathlib import Path
out = Path("$OUT")
long_acc = (out / "LONG_ACCEPTANCE.md").read_text(errors="replace") if (out / "LONG_ACCEPTANCE.md").is_file() else ""
soak_log = Path("$LOG/soak.out").read_text(errors="replace") if Path("$LOG/soak.out").is_file() else ""

def flag(text, key):
    m = re.search(rf"^{key}=(.+)$", text, re.M)
    return m.group(1).strip() if m else None

long_ok = flag(long_acc, "ok") == "True"
long_passed = "passed=True" in long_acc
elapsed = flag(long_acc, "elapsed_s")
soak_ok = $SOAK_RC == 0
if "llm" in soak_log.lower() or "source" in soak_log.lower():
    soak_ok = $SOAK_RC == 0

payload = {
  "suite": "live_long_maturity",
  "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
  "model": "$EGLK_MODEL",
  "base_url": "$EGLK_BASE_URL",
  "bench_sleep_s": int("$EGLK_BENCH_SLEEP_S"),
  "long": {
    "rc": $LONG_RC,
    "ok": long_ok,
    "passed": long_passed,
    "elapsed_s": int(elapsed) if elapsed and elapsed.isdigit() else elapsed,
    "acceptance": str(out / "LONG_ACCEPTANCE.md"),
  },
  "soak": {"rc": $SOAK_RC, "ok": soak_ok, "log": str(Path("$LOG/soak.out"))},
  "passed": bool(long_passed and soak_ok),
  "note": "scores/Gate untouched; mid-abort only cognitive_tokens + repairs_max",
}
(out / "STATUS.json").write_text(json.dumps(payload, indent=2) + "\n")
(out / "LIVE_MATURITY.md").write_text(
    "# Live long maturity\n\n"
    f"- long passed={long_passed} elapsed_s={elapsed} rc={$LONG_RC}\n"
    f"- soak ok={soak_ok} rc={$SOAK_RC}\n"
    f"- **aggregate passed={payload['passed']}**\n\n"
    f"Bench sleep={payload['bench_sleep_s']}s (≥30min bar; extended wall).\n"
    "Never feeds Gate.\n"
)
print(json.dumps(payload, indent=2))
raise SystemExit(0 if payload["passed"] else 1)
PY
