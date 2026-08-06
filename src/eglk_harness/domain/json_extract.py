"""Extract the first JSON object/array from model text."""

from __future__ import annotations

import json
import re
from typing import Any


_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def unwrap_agent_jsonl(text: str) -> str:
    """If stdout is a Codex/Claude NDJSON event stream, return agent message bodies.

    Codex ``exec --json`` emits one JSON object per line (``thread.started``,
    ``item.completed`` with ``agent_message``, …). Schema extraction must run on
    the agent text, not the first stream envelope (which has ``thread_id``/``type``).
    """
    if not text or not text.strip():
        return text

    messages: list[str] = []
    saw_typed_event = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or "type" not in obj:
            continue
        saw_typed_event = True
        item = obj.get("item")
        if obj.get("type") == "item.completed" and isinstance(item, dict):
            if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                messages.append(item["text"])
            continue
        # Some streams expose message text on the top-level event.
        if obj.get("type") in {"agent_message", "message"} and isinstance(obj.get("text"), str):
            messages.append(obj["text"])

    if messages:
        return "\n".join(messages)
    return text if not saw_typed_event else text


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from LLM stdout.

    Prefer unwrapped agent JSONL bodies, then fenced ```json blocks, then first
    ``{...}`` / ``[...]`` span. Raises ``ValueError`` if nothing parses.
    """
    if not text or not text.strip():
        raise ValueError("empty model output")

    text = unwrap_agent_jsonl(text)

    for m in _FENCE.finditer(text):
        chunk = m.group(1).strip()
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue

    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = stripped.find(opener)
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(stripped)):
            ch = stripped[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    chunk = stripped[start : i + 1]
                    try:
                        return json.loads(chunk)
                    except json.JSONDecodeError:
                        break
    raise ValueError("no JSON object/array found in model output")
