"""Short en/zh constraint blocks appended to bypass role prompts."""

from __future__ import annotations

import os
from typing import Mapping

_BLOCKS = {
    "en": (
        "CONSTRAINTS:\n"
        "- No tools. No MCP. No shell.\n"
        "- Return a single JSON object only.\n"
        "- You do not admit or reject claims; Gate is mechanical."
    ),
    "zh": (
        "约束：\n"
        "- 无工具。无 MCP。无 shell。\n"
        "- 只返回一个 JSON 对象。\n"
        "- 你不 admit/reject Claim；Gate 是机械判决。"
    ),
}


def prompt_language(env: Mapping[str, str] | None = None) -> str:
    env = env or os.environ
    raw = (env.get("EGLK_PROMPT_LANGUAGE") or "en").strip().lower()
    if raw.startswith("zh") or raw in {"cn", "chinese"}:
        return "zh"
    return "en"


def constraint_block(env: Mapping[str, str] | None = None) -> str:
    return _BLOCKS[prompt_language(env)]
