"""Plugin state store under EGLK_PLUGINS_ROOT."""

from __future__ import annotations


def test_record_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("EGLK_PLUGINS_ROOT", str(tmp_path))
    from eglk_harness.domain.plugins import state

    state.record_install(
        "codex-computer-use",
        agents=["codex"],
        version="1",
    )
    installed = state.installed_plugins()
    assert "codex-computer-use" in installed
    assert "codex" in installed["codex-computer-use"].agents


def test_write_mcp_config_json(tmp_path, monkeypatch):
    monkeypatch.setenv("EGLK_PLUGINS_ROOT", str(tmp_path))
    from eglk_harness.domain.plugins import state

    path = state.write_mcp_config(
        "open-computer-use",
        "claude_code",
        server_name="open-computer-use",
        command="open-computer-use",
        args=["mcp"],
    )
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "mcpServers" in text
    assert "open-computer-use" in text
