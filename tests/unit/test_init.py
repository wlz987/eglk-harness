"""Tests for ``eglk-harness init`` scaffolding."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.init_project import init_project
from eglk_harness.domain import paths


def test_init_creates_skeleton(tmp_path: Path) -> None:
    result = init_project(tmp_path)
    assert paths.config_path(tmp_path).is_file()
    assert paths.goal_path(tmp_path).is_file()
    assert paths.loop_root(tmp_path).is_dir()
    assert paths.memory_sigma_dir(tmp_path).is_dir()
    assert (paths.memory_sigma_dir(tmp_path) / "active.json").is_file()
    assert " .eglk-harness/config.toml".strip() in " ".join(result.created) or any(
        p.endswith("config.toml") for p in result.created
    )


def test_init_idempotent_without_force(tmp_path: Path) -> None:
    init_project(tmp_path)
    paths.goal_path(tmp_path).write_text("# custom\n", encoding="utf-8")
    result = init_project(tmp_path, force=False)
    assert paths.goal_path(tmp_path).read_text(encoding="utf-8") == "# custom\n"
    assert any(p.endswith(".goal.md") for p in result.skipped)
    assert not any(p.endswith(".goal.md") for p in result.created)


def test_init_force_overwrites(tmp_path: Path) -> None:
    init_project(tmp_path)
    paths.goal_path(tmp_path).write_text("# custom\n", encoding="utf-8")
    result = init_project(tmp_path, force=True)
    assert "# Goal" in paths.goal_path(tmp_path).read_text(encoding="utf-8")
    assert any(p.endswith(".goal.md") for p in result.created)
