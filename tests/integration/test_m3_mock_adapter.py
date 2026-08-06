"""M3: mock adapter through full tick (Maker/Checker via AgentAdapter)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from eba import ActorId, Bus, Inbox, make_envelope, run_actors

from eglk_harness.actors.checker import CheckerActor
from eglk_harness.actors.gate import GateActor
from eglk_harness.actors.host import RunHost
from eglk_harness.actors.maker import MakerActor
from eglk_harness.actors.tick import TickJob
from eglk_harness.domain.adapters import MockAdapter
from eglk_harness.domain import loop_store, paths
from eglk_harness.domain.init_project import init_project
from eglk_harness.protocol import keys, topics


async def _tick(workdir: Path, *, mode: str = "admit") -> TickJob:
    init_project(workdir)
    goal_id = "g-m3"
    adapter = MockAdapter(mode=mode)
    bus = Bus()
    maker = MakerActor(
        actor_id=ActorId(keys.MAKER),
        bus=bus,
        inbox=Inbox(32),
        adapter=adapter,
        workdir=workdir,
        tools_allowed=True,
    )
    checker = CheckerActor(
        actor_id=ActorId(keys.CHECKER),
        bus=bus,
        inbox=Inbox(32),
        adapter=adapter,
        workdir=workdir,
        tools_allowed=True,
    )
    gate = GateActor(actor_id=ActorId(keys.GATE), bus=bus, inbox=Inbox(32))
    host = RunHost(
        actor_id=ActorId(keys.HOST),
        bus=bus,
        inbox=Inbox(32),
        job_factory=TickJob,
        workdir=workdir,
        goal_id=goal_id,
        goal_title="m3",
        done_criteria=["hello.txt exists"],
        request_timeout=15.0,
    )

    async def work() -> TickJob:
        await bus.publish(
            make_envelope(
                topic=topics.RUN_START,
                payload={"args": {"tick": 0, "goal_id": goal_id}},
                sender=ActorId("test"),
            )
        )
        async with asyncio.timeout(15):
            while not (host.jobs and host.jobs[0].finished):
                await asyncio.sleep(0.005)
        job = host.jobs[0]
        assert isinstance(job, TickJob)
        return job

    return await run_actors([maker, checker, gate, host], work, grace=1.0)


@pytest.mark.asyncio
async def test_mock_adapter_tick_admit(tmp_path: Path) -> None:
    job = await _tick(tmp_path, mode="admit")
    assert job.decision and job.decision["decision"] == "admit"
    assert (tmp_path / "hello.txt").is_file()
    tree = loop_store.load_tree(paths.loop_goal_dir(tmp_path, "g-m3"))
    assert tree and tree.all_work_admitted()


@pytest.mark.asyncio
async def test_app_rejects_mcp_on_non_tool_role_assembly() -> None:
    from eglk_harness.domain.adapters.base import EpisodeRequest

    with pytest.raises(AssertionError):
        EpisodeRequest(
            role="governor",
            prompt="x",
            workdir=Path("."),
            tools_allowed=True,
        )
