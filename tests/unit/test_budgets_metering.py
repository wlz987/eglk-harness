from eglk_harness.domain.runtime.budgets import timeout_for_role
from eglk_harness.domain.adapters.mcp import resolve_mcp_config


def test_timeout_for_role_reads_env(monkeypatch):
    monkeypatch.setenv("EGLK_TIMEOUT_GOVERNOR", "77")
    assert timeout_for_role("governor") == 77.0


def test_resolve_mcp_prefers_cli(tmp_path, monkeypatch):
    monkeypatch.delenv("EGLK_MCP_CONFIG", raising=False)
    p = tmp_path / "mcp.json"
    p.write_text('{"mcpServers":{}}', encoding="utf-8")
    assert resolve_mcp_config(p) == p


def test_resolve_mcp_plugin_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("EGLK_MCP_CONFIG", raising=False)
    monkeypatch.setenv("EGLK_PLUGINS_ROOT", str(tmp_path))
    from eglk_harness.domain.plugins import state

    cfg = state.write_mcp_config(
        "open-computer-use",
        "claude_code",
        server_name="open-computer-use",
        command="open-computer-use",
        args=["mcp"],
    )
    state.record_install(
        "open-computer-use",
        agents=["claude_code"],
        mcp_configs={"claude_code": str(cfg)},
        mcp_server_name="open-computer-use",
    )
    resolved = resolve_mcp_config(None, agent="claude_code")
    assert resolved is not None
    assert resolved.is_file()
