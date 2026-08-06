"""CLI smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.cli import main


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as ei:
        main(["--help"])
    assert ei.value.code == 0


def test_init_via_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as ei:
        main(["init", "--workdir", str(tmp_path)])
    assert ei.value.code == 0
    assert (tmp_path / ".eglk-harness" / "config.toml").is_file()
    assert (tmp_path / ".goal.md").is_file()


def test_status_via_cli(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as ei:
        main(["status", "--workdir", str(tmp_path)])
    assert ei.value.code == 0


def test_doctor_via_cli(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as ei:
        main(["doctor", "--workdir", str(tmp_path)])
    assert ei.value.code == 0
