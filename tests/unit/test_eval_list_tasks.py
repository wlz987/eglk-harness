"""eval --list-tasks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eglk_harness.cli import main


def test_list_tasks_wa_hard(capsys: pytest.CaptureFixture[str]) -> None:
    eval_root = Path("/home/wlz/alw/experiment/eval")
    if not (eval_root / "wa_hard" / "pack.json").is_file():
        pytest.skip("alw eval pack missing")
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
    assert out["count"] >= 5
    assert out["tasks"][0]["id"]


def test_list_tasks_weave_lh(capsys: pytest.CaptureFixture[str]) -> None:
    eval_root = Path("/home/wlz/alw/experiment/eval")
    if not (eval_root / "weave_lh" / "pack.json").is_file():
        pytest.skip("weave_lh pack missing")
    with pytest.raises(SystemExit) as ei:
        main(["eval", "--suite", "weave_lh", "--list-tasks", "--eval-root", str(eval_root)])
    assert ei.value.code == 0
    out = json.loads(capsys.readouterr().out.split("note:")[0])
    assert out["count"] >= 1


def test_list_tasks_tb21(capsys: pytest.CaptureFixture[str]) -> None:
    eval_root = Path("/home/wlz/alw/experiment/eval")
    if not (eval_root / "tb21" / "pack.json").is_file():
        pytest.skip("tb21 pack missing")
    with pytest.raises(SystemExit) as ei:
        main(["eval", "--suite", "tb21", "--list-tasks", "--eval-root", str(eval_root)])
    assert ei.value.code == 0
    out = json.loads(capsys.readouterr().out.split("note:")[0])
    assert out["count"] >= 1
    assert out["tasks"][0]["id"] == "tb21-smoke-001"
