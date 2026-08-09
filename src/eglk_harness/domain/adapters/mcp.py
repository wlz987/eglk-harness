"""MCP config load + Claude/Codex translation (opt-in; role allowlists)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.adapters.tool_policy import (
    assert_tools_for_role,
    resolve_role_tool_profile,
)

# Re-export for callers that imported from mcp historically
__all__ = [
    "assert_tools_for_role",
    "load_mcp_config",
    "resolve_mcp_config",
    "resolve_add_dirs",
    "mcp_servers",
    "filter_mcp_config_for_role",
    "claude_mcp_argv",
    "codex_mcp_overrides",
    "codex_mcp_argv",
]


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
    agent: str | None = None,
) -> Path | None:
    """Resolve MCP config: CLI → env → already-installed plugin (never installs)."""
    env = env or os.environ
    if cli_path is not None:
        return Path(cli_path)
    raw = env.get("EGLK_MCP_CONFIG") or ""
    if raw.strip():
        return Path(raw)
    # Opt-in use of a previously installed computer-use plugin MCP file.
    # ``run`` never installs; empty path (official Codex GUI) is skipped here.
    if agent and agent not in {"mock", "fake"}:
        try:
            from eglk_harness.domain.plugins.state import active_plugin_for_agent

            active = active_plugin_for_agent(agent)
        except Exception:
            active = None
        if active is not None:
            _plugin_id, mcp_path = active
            if mcp_path and Path(mcp_path).is_file():
                return Path(mcp_path)
    return None


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


def filter_mcp_config_for_role(
    mcp_config: Path | None,
    *,
    role: str,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    """Return original path, a filtered temp JSON, or None per role allowlist."""
    if mcp_config is None:
        return None
    profile = resolve_role_tool_profile(role, env=env)
    if not profile.tools_allowed:
        return None
    allow = profile.mcp_server_allowlist
    if allow is None:
        return Path(mcp_config)
    data = load_mcp_config(mcp_config)
    if data is None:
        return None
    servers = mcp_servers(data)
    if not allow:
        # Empty allowlist → no MCP servers (native tools may still be on).
        filtered = {"mcpServers": {}}
    else:
        filtered = {
            "mcpServers": {k: v for k, v in servers.items() if k in allow},
        }
    fd, name = tempfile.mkstemp(prefix=f"eglk-mcp-{role.lower()}-", suffix=".json")
    os.close(fd)
    path = Path(name)
    path.write_text(json.dumps(filtered, indent=2) + "\n", encoding="utf-8")
    return path


def claude_mcp_argv(
    *,
    mcp_config: Path | None,
    add_dirs: list[str],
    tools_allowed: bool,
    role: str,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Claude Code CLI flags for roles whose profile allows tools."""
    assert_tools_for_role(role, tools_allowed=tools_allowed, env=env)
    if not tools_allowed:
        return []
    filtered = filter_mcp_config_for_role(mcp_config, role=role, env=env)
    argv: list[str] = []
    if filtered is not None:
        argv.extend(["--mcp-config", str(filtered)])
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
    env: Mapping[str, str] | None = None,
) -> list[str]:
    assert_tools_for_role(role, tools_allowed=tools_allowed, env=env)
    if not tools_allowed:
        return []
    filtered = filter_mcp_config_for_role(mcp_config, role=role, env=env)
    argv: list[str] = []
    for override in codex_mcp_overrides(filtered):
        argv.extend(["-c", override])
    for d in add_dirs:
        argv.extend(["--add-dir", d])
    return argv
