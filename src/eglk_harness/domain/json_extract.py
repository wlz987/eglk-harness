"""Extract the first JSON object/array from model text."""

from __future__ import annotations

import json
import re
from typing import Any


_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from LLM stdout.

    Prefer fenced ```json blocks, then first ``{...}`` / ``[...]`` span.
    Raises ``ValueError`` if nothing parses.
    """
    if not text or not text.strip():
        raise ValueError("empty model output")

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
