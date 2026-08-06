"""MCP config load + Claude/Codex translation (opt-in; Maker/Checker only)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.adapters.base import TOOL_ROLES


def assert_tools_for_role(role: str, *, tools_allowed: bool) -> None:
    """Hard fail if a non-tool role is assembled with tools/MCP."""
    if tools_allowed and role not in TOOL_ROLES:
        raise AssertionError(
            f"refusing to attach tools/MCP to role={role!r}; "
            f"allowed={sorted(TOOL_ROLES)}"
        )


def load_mcp_config(path: Path | str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"mcp config must be object: {p}")
    return data


def resolve_mcp_config(
    cli_path: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    env = env or os.environ
    if cli_path is not None:
        return Path(cli_path)
    raw = env.get("EGLK_MCP_CONFIG") or ""
    return Path(raw) if raw.strip() else None


def resolve_add_dirs(
    cli_dirs: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    env = env or os.environ
    out: list[str] = list(cli_dirs or [])
    raw = env.get("EGLK_MCP_ADD_DIRS") or ""
    if raw.strip():
        out.extend(part for part in raw.split(os.pathsep) if part.strip())
    # de-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for d in out:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def mcp_servers(data: Mapping[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    servers = data.get("mcpServers")
    return dict(servers) if isinstance(servers, dict) else {}


def claude_mcp_argv(
    *,
    mcp_config: Path | None,
    add_dirs: list[str],
    tools_allowed: bool,
    role: str,
) -> list[str]:
    """Claude Code CLI flags for Maker/Checker only."""
    assert_tools_for_role(role, tools_allowed=tools_allowed)
    if not tools_allowed:
        return []
    argv: list[str] = []
    if mcp_config is not None:
        argv.extend(["--mcp-config", str(mcp_config)])
    for d in add_dirs:
        argv.extend(["--add-dir", d])
    return argv


def _toml_inline(value: Any) -> str:
    if isinstance(value, dict):
        body = ", ".join(f"{k} = {_toml_inline(v)}" for k, v in value.items())
        return "{" + body + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_inline(v) for v in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value))


def _mcp_server_entry(spec: Mapping[str, Any]) -> dict[str, Any] | None:
    url = spec.get("url")
    if isinstance(url, str) and url.strip():
        return {"url": url}
    command = spec.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    entry: dict[str, Any] = {"command": command}
    args = spec.get("args")
    if isinstance(args, list):
        string_args = [str(a) for a in args]
        if string_args:
            entry["args"] = string_args
    env = spec.get("env")
    if isinstance(env, dict) and env:
        entry["env"] = {str(k): str(v) for k, v in env.items()}
    return entry


def codex_mcp_overrides(mcp_config: Path | None) -> list[str]:
    """Translate Claude-style mcp.json → Codex ``-c mcp_servers.*`` overrides."""
    if mcp_config is None:
        return []
    data = load_mcp_config(mcp_config)
    overrides: list[str] = []
    for name, spec in mcp_servers(data).items():
        if not isinstance(spec, dict) or not str(name).strip():
            continue
        entry = _mcp_server_entry(spec)
        if entry:
            overrides.append(f"mcp_servers.{name}={_toml_inline(entry)}")
    return overrides


def codex_mcp_argv(
    *,
    mcp_config: Path | None,
    add_dirs: list[str],
    tools_allowed: bool,
    role: str,
) -> list[str]:
    assert_tools_for_role(role, tools_allowed=tools_allowed)
    if not tools_allowed:
        return []
    argv: list[str] = []
    for override in codex_mcp_overrides(mcp_config):
        argv.extend(["-c", override])
    for d in add_dirs:
        argv.extend(["--add-dir", d])
    return argv
