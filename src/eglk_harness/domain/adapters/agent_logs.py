"""Extract human-visible agent transcript text from Codex/Claude JSONL."""

from __future__ import annotations

import json
from typing import Any


def visible_output(raw: str) -> str:
    """Best-effort readable text from Adapter stdout (NDJSON or plain)."""
    if not raw or not raw.strip():
        return ""
    # Prefer Codex-style JSONL agent_message items
    chunks: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s.startswith("{"):
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        text = _from_codex_event(obj)
        if text:
            chunks.append(text)
            continue
        text = _from_claude_event(obj)
        if text:
            chunks.append(text)
    if chunks:
        return "\n".join(chunks)
    # Fallback: strip fences from whole body
    return raw.strip()


def write_visible_sidecar(tee_path: str | None, raw: str) -> str | None:
    """Write ``*.visible.txt`` next to a tee trajectory; return path or None."""
    if not tee_path:
        return None
    from pathlib import Path

    from eglk_harness.domain.redact import redact_secrets

    src = Path(tee_path)
    out = src.with_suffix(src.suffix + ".visible.txt") if src.suffix else Path(str(src) + ".visible.txt")
    # Prefer: maker_000.jsonl → maker_000.visible.txt
    if src.name.endswith(".jsonl"):
        out = src.with_name(src.name[: -len(".jsonl")] + ".visible.txt")
    text = redact_secrets(visible_output(raw))
    if not text.strip():
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    return str(out)


def _from_codex_event(obj: dict[str, Any]) -> str:
    item = obj.get("item")
    if obj.get("type") == "item.completed" and isinstance(item, dict):
        if item.get("type") == "agent_message":
            return str(item.get("text") or "").strip()
    if obj.get("type") == "agent_message":
        return str(obj.get("text") or "").strip()
    return ""


def _from_claude_event(obj: dict[str, Any]) -> str:
    # stream-json message deltas
    if obj.get("type") == "assistant" and isinstance(obj.get("message"), dict):
        content = obj["message"].get("content")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            return "".join(parts).strip()
    if obj.get("type") == "content_block_delta":
        delta = obj.get("delta")
        if isinstance(delta, dict) and delta.get("type") == "text_delta":
            return str(delta.get("text") or "")
    return ""
