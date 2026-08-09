"""Cognitive token metering from Adapter episode transcripts."""

from __future__ import annotations

import json
from typing import Any

def tokens_from_codex_jsonl(text: str) -> int:
    """Sum input+output tokens from Codex ``exec --json`` turn.completed events."""
    if not text:
        return 0
    total = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") != "turn.completed":
            continue
        usage = obj.get("usage")
        if not isinstance(usage, dict):
            continue
        if usage.get("total_tokens") is not None:
            total += int(usage.get("total_tokens") or 0)
        else:
            total += int(usage.get("input_tokens") or 0)
            total += int(usage.get("output_tokens") or 0)
    return total

def add_tokens(quota: dict[str, Any], delta: int) -> dict[str, Any]:
    out = dict(quota)
    cur = int(out.get("cognitive_tokens") or 0)
    out["cognitive_tokens"] = max(0, cur + max(0, int(delta)))
    if "cognitive_tokens_max" not in out:
        from eglk_harness.domain.kernel import projections as P

        out["cognitive_tokens_max"] = P.COGNITIVE_TOKENS_MAX
    return out

def update_focus_uncertainty(
    *,
    decision: str,
    focus_score: float,
    uncertainty: float,
) -> tuple[float, float]:
    """Mechanical focus/uncertainty update after Gate (never used as abort)."""
    f = float(focus_score)
    u = float(uncertainty)
    kind = str(decision or "")
    if kind == "admit":
        f = min(1.0, f + 0.05)
        u = max(0.0, u - 0.05)
    elif kind == "repair":
        f = max(0.0, f - 0.10)
        u = min(1.0, u + 0.15)
    elif kind == "abort":
        f = max(0.0, f - 0.20)
        u = min(1.0, u + 0.25)
    return round(f, 4), round(u, 4)
