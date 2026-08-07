"""Read-only helpers for Codex MCP TOML blocks (never writes ~/.codex)."""

from __future__ import annotations

import json


def mcp_server_block(name: str, command: str, args: list[str]) -> str:
    lines = [f"[mcp_servers.{name}]", f"command = {json.dumps(command)}"]
    if args:
        lines.append("args = [" + ", ".join(json.dumps(arg) for arg in args) + "]")
    return "\n".join(lines) + "\n"
