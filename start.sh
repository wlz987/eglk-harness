#!/usr/bin/env bash
# Thin wrapper — truth source is `eglk-harness run` (packaging.md).
# Usage (from a project workdir):
#   /path/to/eglk-harness/start.sh --goal .goal.md
#   ./start.sh --agent mock --swarm 0
set -euo pipefail

if ! command -v eglk-harness >/dev/null 2>&1; then
  echo "error: eglk-harness not on PATH — pip install -e /path/to/eglk-harness" >&2
  exit 127
fi

exec eglk-harness run "$@"
