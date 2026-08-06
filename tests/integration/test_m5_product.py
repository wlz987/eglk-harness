"""Product surface: status, start.sh, env.example, toy e2e admit."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.app import RunRequest, run
from eglk_harness.cli import main
from eglk_harness.domain.init_project import init_project
from eglk_harness.domain.status import collect_status


def test_status_after_toy_run(tmp_path: Path) -> None:
    init_project(tmp_path)
    (tmp_path / ".goal.md").write_text(
        "# Toy\n\n## Done criteria\n\n- [ ] hello.txt exists\n",
        encoding="utf-8",
    )
    code = run(
        RunRequest(
            workdir=tmp_path,
            agent="mock",
            swarm="0",
            compile="force",
        )
    )
    assert code == 0
    assert (tmp_path / "hello.txt").is_file()
    assert (tmp_path / ".goal_format.md").is_file()

    report = collect_status(tmp_path)
    text = report.render()
    assert report.selected_run is not None
    assert report.latest_decision is not None
    assert report.latest_decision.get("decision") == "admit"
    assert any(n["status"] == "admitted" for n in report.tree_summary)
    assert report.leaf_contract is not None
    assert "read-only" in text
    assert "approval" in text
    # no HITL knobs in output
    assert "approve" not in text.lower() or "no approval" in text


def test_status_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    init_project(tmp_path)
    with pytest.raises(SystemExit) as ei:
        main(["status", "--workdir", str(tmp_path)])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "read-only" in out
    assert "no approval" in out


def test_start_sh_exists_and_is_executable() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "start.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "eglk-harness run" in text
    assert script.stat().st_mode & 0o111  # executable bit


def test_env_example_present() -> None:
    root = Path(__file__).resolve().parents[2]
    env = root / "env.example"
    assert env.is_file()
    body = env.read_text(encoding="utf-8")
    assert "EGLK_MODEL" in body
    assert "EGLK_MCP_CONFIG" in body
    assert "EGLK_COMPILE" in body
