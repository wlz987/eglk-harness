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
    """Count billable turn tokens without double-counting cache fields.

    Prefer ``input_tokens + output_tokens``. Ignore ``cached_input_tokens`` /
    ``cache_write_input_tokens`` (subsets / side channels of input). Ignore
    ``total_tokens`` when parts are present.
    """
    if usage.get("input_tokens") is not None or usage.get("output_tokens") is not None:
        total = 0
        for key in ("input_tokens", "output_tokens"):
            val = usage.get(key)
            if isinstance(val, (int, float)):
                total += int(val)
        return total
    if usage.get("prompt_tokens") is not None or usage.get("completion_tokens") is not None:
        total = 0
        for key in ("prompt_tokens", "completion_tokens"):
            val = usage.get(key)
            if isinstance(val, (int, float)):
                total += int(val)
        return total
    val = usage.get("total_tokens")
    if isinstance(val, (int, float)):
        return int(val)
    return 0
