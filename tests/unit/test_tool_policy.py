"""Unit tests for role tool profiles (policy 2+3)."""

from __future__ import annotations

import json
from pathlib import Path

from eglk_harness.domain.adapters.base import EpisodeRequest, SESSION_ROLES, TOOL_ROLES
from eglk_harness.domain.adapters.mcp import assert_tools_for_role, filter_mcp_config_for_role
from eglk_harness.domain.adapters.tool_policy import resolve_role_tool_profile


def test_all_session_roles_may_hold_tools_by_default() -> None:
    assert TOOL_ROLES == SESSION_ROLES
    for role in SESSION_ROLES:
        profile = resolve_role_tool_profile(role, env={})
        assert profile.tools_allowed is True
        assert profile.mcp_server_allowlist is None
        assert_tools_for_role(role, tools_allowed=True, env={})


def test_gate_and_unknown_denied() -> None:
    profile = resolve_role_tool_profile("gate", env={})
    assert profile.tools_allowed is False
    try:
        assert_tools_for_role("gate", tools_allowed=True, env={})
        raise AssertionError("expected fail")
    except AssertionError as exc:
        assert "gate" in str(exc)


def test_tools_off_roles_env() -> None:
    env = {"EGLK_TOOLS_OFF_ROLES": "governor,compile"}
    assert resolve_role_tool_profile("governor", env=env).tools_allowed is False
    assert resolve_role_tool_profile("maker", env=env).tools_allowed is True


def test_mcp_allowlist_filters(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "computer-use": {"command": "/bin/echo"},
                    "search": {"command": "/bin/true"},
                }
            }
        ),
        encoding="utf-8",
    )
    env = {"EGLK_MCP_ALLOW_GOVERNOR": "search"}
    filtered = filter_mcp_config_for_role(cfg, role="governor", env=env)
    assert filtered is not None
    data = json.loads(filtered.read_text(encoding="utf-8"))
    assert set(data["mcpServers"]) == {"search"}


def test_mcp_allowlist_none_means_empty_servers(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp.json"
    cfg.write_text('{"mcpServers":{"computer-use":{"command":"/bin/echo"}}}\n', encoding="utf-8")
    env = {"EGLK_MCP_ALLOW_EXPLORER": "none"}
    filtered = filter_mcp_config_for_role(cfg, role="explorer", env=env)
    assert filtered is not None
    data = json.loads(filtered.read_text(encoding="utf-8"))
    assert data["mcpServers"] == {}


def test_episode_request_allows_governor_tools(tmp_path: Path) -> None:
    req = EpisodeRequest(
        role="governor",
        prompt="x",
        workdir=tmp_path,
        tools_allowed=True,
    )
    assert req.tools_allowed is True
