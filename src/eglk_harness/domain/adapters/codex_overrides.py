"""Codex ``-c`` provider / MCP override helpers (LH-shaped)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_PROVIDER_ID = "eglk_harness"
_DEFAULT_BASE_URL = "https://api.openai.com/v1"


def provider_overrides(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[str]:
    """Build ``-c key=value`` overrides that point Codex at an OpenAI-compatible endpoint."""
    base_url = base_url or os.environ.get("EGLK_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    api_key = api_key or os.environ.get("EGLK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not base_url and not api_key:
        return []
    provider: dict[str, Any] = {
        "name": "eglk-harness",
        "base_url": _normalize_base_url(base_url),
        "wire_api": os.environ.get("EGLK_WIRE_API") or "responses",
    }
    if api_key:
        provider["env_key"] = "OPENAI_API_KEY"
    return [
        f"model_providers.{_PROVIDER_ID}={_toml_inline(provider)}",
        f"model_provider={json.dumps(_PROVIDER_ID)}",
    ]


def mcp_config_overrides(path: Path | str) -> list[str]:
    """Translate Claude-style ``mcp.json`` into Codex ``mcp_servers`` ``-c`` overrides."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return []
    overrides: list[str] = []
    for name, spec in servers.items():
        if not isinstance(spec, dict) or not str(name).strip():
            continue
        entry = _mcp_server_entry(spec)
        if entry:
            overrides.append(f"mcp_servers.{name}={_toml_inline(entry)}")
    return overrides


def _normalize_base_url(base_url: str | None) -> str:
    if not base_url:
        return _DEFAULT_BASE_URL
    trimmed = base_url.rstrip("/")
    return trimmed if trimmed.endswith("/v1") else f"{trimmed}/v1"


def _mcp_server_entry(spec: dict[str, Any]) -> dict[str, Any] | None:
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
