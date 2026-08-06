"""M3: mock adapter through full tick."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.domain import loop_store, paths
from eglk_harness.domain.adapters.base import EpisodeRequest
from helpers.tick_runtime import run_tick


@pytest.mark.asyncio
async def test_mock_adapter_tick_admit(tmp_path: Path) -> None:
    job = await run_tick(tmp_path, goal_id="g-m3", mode="admit", swarm_soft="0", use_fake=False)
    assert job.decision and job.decision["decision"] == "admit"
    assert (tmp_path / "hello.txt").is_file()
    tree = loop_store.load_tree(paths.loop_goal_dir(tmp_path, "g-m3"))
    assert tree and tree.all_work_admitted()


@pytest.mark.asyncio
async def test_app_rejects_mcp_on_non_tool_role_assembly() -> None:
    with pytest.raises(AssertionError):
        EpisodeRequest(
            role="governor",
            prompt="x",
            workdir=Path("."),
            tools_allowed=True,
        )
