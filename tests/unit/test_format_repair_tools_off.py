"""Format-repair must not re-open tools (avoids re-running long benches)."""

from __future__ import annotations

import ast
from pathlib import Path

from eglk_harness.domain.runtime.format_repair import repair_prompt


def test_repair_prompt_forbids_tool_rerun() -> None:
    text = repair_prompt(role="maker", leaf_block="[LEAF]", previous_error="unparseable")
    assert "re-run tools" in text or "Do **not** re-run" in text
    assert "JSON" in text


def test_format_repair_episode_request_disables_tools() -> None:
    src = Path(__file__).resolve().parents[2] / "src/eglk_harness/domain/runtime/format_repair.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # EpisodeRequest(... tools_allowed=False ...)
            for kw in node.keywords:
                if kw.arg == "tools_allowed" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                    found = True
    assert found, "format_repair must construct EpisodeRequest(tools_allowed=False)"
