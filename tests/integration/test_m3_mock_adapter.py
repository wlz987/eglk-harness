"""Integration: MockAdapter-backed Maker/Checker through a full tick."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.domain import loop_store, paths
from eglk_harness.domain.adapters.base import EpisodeRequest
from helpers.tick_runtime import run_tick


@pytest.mark.asyncio
async def test_mock_adapter_tick_admit(tmp_path: Path) -> None:
    job = await run_tick(tmp_path, goal_id="g-adapter", mode="admit", swarm_soft="0")
    assert job.decision and job.decision["decision"] == "admit"
    assert (tmp_path / "hello.txt").is_file()
    tree = loop_store.load_tree(paths.loop_goal_dir(tmp_path, "g-adapter"))
    assert tree and tree.all_work_admitted()


def test_episode_request_rejects_tools_on_governor() -> None:
    with pytest.raises(AssertionError):
        EpisodeRequest(
            role="governor",
            prompt="x",
            workdir=Path("."),
            tools_allowed=True,
        )
