"""Best-effort token / USD metering from agent CLI JSONL."""

from __future__ import annotations

import json
from typing import Any


def tokens_and_cost_from_codex_jsonl(raw: str) -> tuple[int, float]:
    """Sum usage from Codex turn.completed events; return (tokens, cost_usd)."""
    tokens = 0
    cost = 0.0
    for line in str(raw or "").splitlines():
        s = line.strip()
        if not s.startswith("{"):
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "turn.completed":
            usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
            tokens += _usage_tokens(usage)
            if "total_cost_usd" in obj:
                try:
                    cost += float(obj["total_cost_usd"])
                except (TypeError, ValueError):
                    pass
        if obj.get("type") == "result":
            # Claude stream-json result
            if "total_cost_usd" in obj:
                try:
                    cost += float(obj["total_cost_usd"])
                except (TypeError, ValueError):
                    pass
            usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
            tokens += _usage_tokens(usage)
    return tokens, cost


def tokens_and_cost_from_raw(raw: str) -> tuple[int, float]:
    """Detect format lightly and meter; (0, 0.0) if absent."""
    return tokens_and_cost_from_codex_jsonl(raw)


def _usage_tokens(usage: dict[str, Any]) -> int:
    total = 0
    for key in (
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
    ):
        val = usage.get(key)
        if isinstance(val, (int, float)):
            # Avoid double-counting total_tokens with parts: prefer parts
            if key == "total_tokens" and (
                usage.get("input_tokens") is not None or usage.get("output_tokens") is not None
            ):
                continue
            total += int(val)
    return total
