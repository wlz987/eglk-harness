"""Read-only helpers for Codex MCP TOML blocks (never writes ~/.codex)."""

from __future__ import annotations

import json
import os
from pathlib import Path


def codex_config_path() -> Path:
    home = os.environ.get("CODEX_HOME") or Path.home() / ".codex"
    return Path(home).expanduser() / "config.toml"


def mcp_server_block(name: str, command: str, args: list[str]) -> str:
    lines = [f"[mcp_servers.{name}]", f"command = {json.dumps(command)}"]
    if args:
        lines.append("args = [" + ", ".join(json.dumps(arg) for arg in args) + "]")
    return "\n".join(lines) + "\n"
