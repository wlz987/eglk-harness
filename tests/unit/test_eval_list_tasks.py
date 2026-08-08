"""eval --list-tasks."""

from __future__ import annotations

import json

import pytest

from eglk_harness.cli import main
from tests.helpers.eval_root import eval_root_for_tests


def test_list_tasks_wa_hard(capsys: pytest.CaptureFixture[str]) -> None:
    eval_root = eval_root_for_tests()
    with pytest.raises(SystemExit) as ei:
        main(
            [
                "eval",
                "--suite",
                "wa_hard",
                "--list-tasks",
                "--eval-root",
                str(eval_root),
            ]
        )
    assert ei.value.code == 0
    out = json.loads(capsys.readouterr().out.split("note:")[0])
    assert out["count"] >= 3
    assert out["tasks"][0]["id"]


def test_list_tasks_weave_lh(capsys: pytest.CaptureFixture[str]) -> None:
    eval_root = eval_root_for_tests()
    with pytest.raises(SystemExit) as ei:
        main(["eval", "--suite", "weave_lh", "--list-tasks", "--eval-root", str(eval_root)])
    assert ei.value.code == 0
    out = json.loads(capsys.readouterr().out.split("note:")[0])
    assert out["count"] >= 1


def test_list_tasks_tb21(capsys: pytest.CaptureFixture[str]) -> None:
    eval_root = eval_root_for_tests()
    with pytest.raises(SystemExit) as ei:
        main(["eval", "--suite", "tb21", "--list-tasks", "--eval-root", str(eval_root)])
    assert ei.value.code == 0
    out = json.loads(capsys.readouterr().out.split("note:")[0])
    assert out["count"] >= 1
    assert out["tasks"][0]["id"]
