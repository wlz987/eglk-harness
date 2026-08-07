"""Unit tests for weave_lh connector."""

from __future__ import annotations

import json
from pathlib import Path

from eglk_harness.domain.eval import weave_lh as wl


def test_score_from_judge_result(tmp_path: Path) -> None:
    p = tmp_path / "judge.json"
    p.write_text(json.dumps({"scores": {"success": 1.0, "pass": 1.0}, "task_id": "t1"}), encoding="utf-8")
    scores = wl.score_from_judge_result(p)
    assert scores["success"] == 1.0
    assert scores["status"] == "external_scored"
    assert "admit" not in scores


def test_materialize_and_placeholder(tmp_path: Path) -> None:
    task = wl.WeaveLhTask(task_id="weave-smoke-001", summary="open notepad")
    goal = wl.materialize_goal(task, tmp_path)
    assert goal.is_file()
    scores = wl.score_placeholder(task_id=task.task_id, workdir=tmp_path, eval_root=tmp_path)
    assert scores["suite"] == "weave_lh"
    assert "vendor" in scores


def test_vendor_status_never_raises(tmp_path: Path) -> None:
    st = wl.vendor_status(tmp_path)
    assert "vendor_ready" in st
