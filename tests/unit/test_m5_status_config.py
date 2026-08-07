"""Unit tests for config resolve + status helpers."""

from __future__ import annotations

import json
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


def test_status_surfaces_tick_and_decisions(tmp_path: Path) -> None:
    init_project(tmp_path)
    loop = tmp_path / ".eglk-harness" / "loop" / "g-test"
    (loop / "decisions").mkdir(parents=True)
    (loop / "decisions" / "0001.json").write_text(
        '{"decision":"repair","reason":"x","tick":0}\n', encoding="utf-8"
    )
    (loop / "state.json").write_text(
        '{"tick": 2, "focus_score": 0.4, "uncertainty": 0.2, "quota": {"cognitive_tokens": 10}}\n',
        encoding="utf-8",
    )
    (loop / "subgoals_tree.json").write_text(
        json.dumps(
            {
                "subgoals_tree": {
                    "id": "root",
                    "title": "t",
                    "status": "open",
                    "done_criteria": [],
                    "children": [],
                    "parent_id": None,
                    "repair_streak": 0,
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = collect_status(tmp_path)
    text = report.render()
    assert report.decision_count == 1
    assert report.tick == 2
    assert "τ_focus/τ_unc signal only" in text
    assert "n=1" in text
