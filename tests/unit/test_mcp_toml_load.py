"""Codex plugin MCP is TOML; loaders must not JSON-decode it into explorer_failed."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.adapters.mcp import codex_mcp_overrides, load_mcp_config, mcp_servers


def test_load_codex_plugin_toml(tmp_path: Path):
    p = tmp_path / "open-computer-use.toml"
    p.write_text(
        '[mcp_servers.open-computer-use]\ncommand = "open-computer-use"\nargs = ["mcp"]\n',
        encoding="utf-8",
    )
    data = load_mcp_config(p)
    assert data is not None
    servers = mcp_servers(data)
    assert "open-computer-use" in servers
    assert servers["open-computer-use"]["command"] == "open-computer-use"
    overrides = codex_mcp_overrides(p)
    assert any(o.startswith("mcp_servers.open-computer-use=") for o in overrides)


def test_load_invalid_mcp_returns_none(tmp_path: Path):
    p = tmp_path / "broken.json"
    p.write_text("{not-json", encoding="utf-8")
    assert load_mcp_config(p) is None
    assert codex_mcp_overrides(p) == []
