"""Integration: one tick writes loop artifacts and advances/rolls back the tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.domain.kernel import loop_store
from eglk_harness.domain.kernel import paths
from helpers.tick_runtime import run_tick


@pytest.mark.asyncio
async def test_tick_admit_writes_loop_artifacts(tmp_path: Path) -> None:
    job = await run_tick(tmp_path, mode="admit", swarm_soft="0")
    assert job.outcome and job.outcome["ok"] is True
    assert job.decision and job.decision["decision"] == "admit"

    loop_dir = paths.loop_goal_dir(tmp_path, "g-test")
    assert (loop_dir / "claims" / "000.json").is_file()
    assert (loop_dir / "evidence" / "000.json").is_file()
    assert (loop_dir / "decisions" / "000.json").is_file()
    assert (tmp_path / "hello.txt").is_file()
    assert "hello from mock maker" in (tmp_path / "hello.txt").read_text(encoding="utf-8")

    tree = loop_store.load_tree(loop_dir)
    assert tree is not None
    assert tree.root.status == "admitted"
    assert tree.all_work_admitted()
    assert (loop_dir / "ticks.jsonl").is_file()


@pytest.mark.asyncio
async def test_tick_repair_rolls_back_world(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("keep\n", encoding="utf-8")
    job = await run_tick(tmp_path, mode="repair_integrity", swarm_soft="0")
    assert job.outcome and job.outcome["ok"] is True
    assert job.decision and job.decision["decision"] == "repair"
    assert job.decision["reason"] == "integrity_violation"

    assert not (tmp_path / "hello.txt").exists()
    assert (tmp_path / "keep.txt").read_text(encoding="utf-8") == "keep\n"

    loop_dir = paths.loop_goal_dir(tmp_path, "g-test")
    tree = loop_store.load_tree(loop_dir)
    assert tree is not None
    assert tree.root.status == "in_progress"
    assert tree.root.repair_streak == 1
