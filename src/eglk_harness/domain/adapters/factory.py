"""Factory for AgentAdapter backends."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eglk_harness.domain.adapters.base import AgentAdapter
from eglk_harness.domain.adapters.claude_code import ClaudeCodeAdapter
from eglk_harness.domain.adapters.codex import CodexAdapter
from eglk_harness.domain.adapters.mock import MockAdapter


def create_adapter(
    name: str,
    *,
    model: str | None = None,
    mcp_config: Path | None = None,
    add_dirs: list[str] | None = None,
    mock_mode: str = "admit",
) -> AgentAdapter:
    key = name.strip().lower().replace("-", "_")
    if key in {"mock", "fake"}:
        return MockAdapter(mode=mock_mode)
    if key in {"codex"}:
        return CodexAdapter(model=model, mcp_config=mcp_config, add_dirs=add_dirs)
    if key in {"claude", "claude_code", "claude-code"}:
        return ClaudeCodeAdapter(model=model, mcp_config=mcp_config, add_dirs=add_dirs)
    raise ValueError(f"unknown agent backend: {name!r}")


def adapter_names() -> tuple[str, ...]:
    return ("codex", "claude_code", "mock")
