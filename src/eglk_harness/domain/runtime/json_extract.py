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


_PROTOCOL_KEYS = frozenset({"thread_id", "session_id"})
_PROTOCOL_TYPES = frozenset(
    {
        "thread.started",
        "item.completed",
        "response.completed",
        "response",
        "message",
        "agent_message",
    }
)


def _unwrap_list(val: Any) -> Any:
    """Unwrap single-element lists; prefer domain objects inside lists."""
    if not isinstance(val, list):
        return val
    for item in val:
        if isinstance(item, dict) and ("claim_id" in item or "evidence_id" in item):
            return item
    if len(val) == 1 and isinstance(val[0], dict):
        return val[0]
    return val


def _prefer_domain_object(candidates: list[Any]) -> Any | None:
    """Prefer Claim/Evidence objects over bare arrays or protocol envelopes."""
    if not candidates:
        return None

    def score(val: Any) -> int:
        val = _unwrap_list(val)
        if isinstance(val, dict):
            if "claim_id" in val or "evidence_id" in val:
                return 6
            if "kind" in val and "payload" in val:
                return 5
            if "gaps" in val or "audit_progress" in val or "artifacts" in val:
                return 4
            # Codex / agent protocol envelopes — never treat as Claim
            if "thread_id" in val or val.get("type") in _PROTOCOL_TYPES:
                if not ({"kind", "payload", "gaps"} & set(val)):
                    return -2
            if _PROTOCOL_KEYS & set(val) and "claim_id" not in val and "evidence_id" not in val:
                if "kind" not in val and "gaps" not in val:
                    return -1
            return 2
        if isinstance(val, list):
            return 0
        return -1

    # Stable: among equal scores, prefer later candidates (later agent messages)
    best_i = 0
    best_s = score(candidates[0])
    for i, cand in enumerate(candidates[1:], start=1):
        s = score(cand)
        if s >= best_s:
            best_s = s
            best_i = i
    if best_s < 0:
        return None
    return _unwrap_list(candidates[best_i])


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

    Prefer unwrapped agent JSONL bodies (later messages first), then fenced
    ```json blocks, then balanced ``{...}`` / ``[...]`` spans. Prefer Claim/Evidence
    objects over arrays / protocol envelopes. Raises ``ValueError`` if nothing parses.
    """
    if not text or not text.strip():
        raise ValueError("empty model output")

    bodies = agent_message_bodies(text)
    # Later agent messages first — models often emit chatter then the real Claim
    corpus: list[str]
    if bodies:
        corpus = list(reversed(bodies))
        corpus.append("\n".join(bodies))
    else:
        corpus = [text]

    candidates: list[Any] = []
    for chunk in corpus:
        candidates.extend(_candidates_from_text(chunk))

    chosen = _prefer_domain_object(candidates)
    if isinstance(chosen, dict):
        return chosen
    raise ValueError("no JSON object found in model output")
