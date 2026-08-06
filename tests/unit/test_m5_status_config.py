"""Unit tests for config resolve + status helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.domain.product.config_resolve import resolve_agent, resolve_compile, resolve_swarm
from eglk_harness.domain.product.init_project import init_project
from eglk_harness.domain.product.status import collect_status


def test_resolve_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    init_project(tmp_path)
    cfg = tmp_path / ".eglk-harness" / "config.toml"
    text = cfg.read_text(encoding="utf-8").replace(
        'default_agent = "codex"', 'default_agent = "claude_code"'
    )
    cfg.write_text(text, encoding="utf-8")
    monkeypatch.delenv("EGLK_AGENT", raising=False)
    assert resolve_agent(None, tmp_path, env={}) == "claude_code"
    assert resolve_agent("mock", tmp_path, env={}) == "mock"
    assert resolve_agent(None, tmp_path, env={"EGLK_AGENT": "codex"}) == "codex"
    assert resolve_swarm(None, env={"EGLK_SWARM": "0"}) == "0"
    assert resolve_compile("force", tmp_path) == "force"


def test_status_empty_workdir(tmp_path: Path) -> None:
    report = collect_status(tmp_path)
    assert report.harness_present is False
    assert "no loop run" in " ".join(report.notes)
