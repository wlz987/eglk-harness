"""Extract the first JSON object/array from model text."""

from __future__ import annotations

import json
import re
from typing import Any


_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def agent_message_bodies(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    messages: list[str] = []
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
        item = obj.get("item")
        if obj.get("type") == "item.completed" and isinstance(item, dict):
            if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                messages.append(item["text"])
            continue
        if obj.get("type") in {"agent_message", "message"} and isinstance(obj.get("text"), str):
            messages.append(obj["text"])
    return messages


def unwrap_agent_jsonl(text: str) -> str:
    """If stdout is a Codex/Claude NDJSON event stream, return agent message bodies."""
    msgs = agent_message_bodies(text)
    if msgs:
        return "\n".join(msgs)
    return text


def _scan_balanced(stripped: str, opener: str, closer: str) -> list[Any]:
    out: list[Any] = []
    start = 0
    while True:
        start = stripped.find(opener, start)
        if start < 0:
            break
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
                        out.append(json.loads(chunk))
                    except json.JSONDecodeError:
                        pass
                    start = i + 1
                    break
        else:
            break
    return out


def _prefer_domain_object(candidates: list[Any]) -> Any | None:
    """Prefer Claim/Evidence objects over bare arrays or unrelated JSON."""
    if not candidates:
        return None

    def score(val: Any) -> int:
        if isinstance(val, dict):
            if "claim_id" in val or "evidence_id" in val:
                return 3
            return 2
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict) and ("claim_id" in item or "evidence_id" in item):
                    return 1
            if len(val) == 1 and isinstance(val[0], dict):
                return 1
            return 0
        return -1

    best = max(candidates, key=score)
    if isinstance(best, list):
        for item in best:
            if isinstance(item, dict) and ("claim_id" in item or "evidence_id" in item):
                return item
        if len(best) == 1 and isinstance(best[0], dict):
            return best[0]
    return best


def _candidates_from_text(text: str) -> list[Any]:
    candidates: list[Any] = []
    for m in _FENCE.finditer(text):
        chunk = m.group(1).strip()
        try:
            candidates.append(json.loads(chunk))
        except json.JSONDecodeError:
            continue
    stripped = text.strip()
    try:
        candidates.append(json.loads(stripped))
    except json.JSONDecodeError:
        pass
    candidates.extend(_scan_balanced(stripped, "{", "}"))
    candidates.extend(_scan_balanced(stripped, "[", "]"))
    return candidates


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from LLM stdout.

    Prefer unwrapped agent JSONL bodies (each message tried separately), then fenced
    ```json blocks, then balanced ``{...}`` / ``[...]`` spans. Prefer Claim/Evidence
    objects over arrays. Raises ``ValueError`` if nothing parses.
    """
    if not text or not text.strip():
        raise ValueError("empty model output")

    bodies = agent_message_bodies(text)
    corpus = [*bodies, "\n".join(bodies)] if bodies else [text]

    candidates: list[Any] = []
    for chunk in corpus:
        candidates.extend(_candidates_from_text(chunk))

    chosen = _prefer_domain_object(candidates)
    if isinstance(chosen, dict):
        return chosen
    if chosen is not None and not isinstance(chosen, (list, dict)):
        return chosen
    raise ValueError("no JSON object found in model output")
