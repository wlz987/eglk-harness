"""Unit tests for tb21 connector."""

from __future__ import annotations

import json
from pathlib import Path

from eglk_harness.domain.eval import EVAL_SUITES
from eglk_harness.domain.eval import tb21 as tb


def test_tb21_in_eval_suites() -> None:
    assert "tb21" in EVAL_SUITES


def test_score_from_judge_result(tmp_path: Path) -> None:
    p = tmp_path / "judge.json"
    p.write_text(
        json.dumps({"scores": {"success": 1.0, "pass": 1.0}, "task_id": "t1", "admit": True}),
        encoding="utf-8",
    )
    scores = tb.score_from_judge_result(p)
    assert scores["success"] == 1.0
    assert scores["status"] == "external_scored"
    assert scores["suite"] == "tb21"
    assert "admit" not in scores
    assert "gate" not in scores


def test_materialize_and_placeholder(tmp_path: Path) -> None:
    task = tb.Tb21Task(task_id="tb21-smoke-001", summary="echo hello")
    goal = tb.materialize_goal(task, tmp_path)
    assert goal.is_file()
    scores = tb.score_placeholder(task_id=task.task_id, workdir=tmp_path, eval_root=tmp_path)
    assert scores["suite"] == "tb21"
    assert "vendor" in scores


def test_load_pack_from_eval_root() -> None:
    eval_root = Path("/home/wlz/alw/experiment/eval")
    if not (eval_root / "tb21" / "pack.json").is_file():
        return
    tasks = tb.load_pack_index(eval_root)
    assert any(t.task_id == "tb21-smoke-001" for t in tasks)


def test_vendor_status_never_raises(tmp_path: Path) -> None:
    st = tb.vendor_status(tmp_path)
    assert "vendor_ready" in st
    assert isinstance(st["vendor_ready"], bool)
