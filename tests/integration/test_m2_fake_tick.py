"""M2 integration: one fake tick writes loop artifacts via eba / eba_job."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from eba import ActorId, Bus, Inbox, make_envelope, run_actors

from eglk_harness.actors.checker import FakeCheckerActor
from eglk_harness.actors.gate import GateActor
from eglk_harness.actors.host import RunHost
from eglk_harness.actors.maker import FakeMakerActor
from eglk_harness.actors.tick import TickJob
from eglk_harness.domain import loop_store, paths
from eglk_harness.domain.init_project import init_project
from eglk_harness.protocol import keys, topics


async def _one_tick(workdir: Path, *, mode: str = "admit", tick: int = 0) -> TickJob:
    init_project(workdir)
    goal_id = "g-test"
    bus = Bus()
    maker = FakeMakerActor(
        actor_id=ActorId(keys.MAKER), bus=bus, inbox=Inbox(32), mode=mode
    )
    checker = FakeCheckerActor(
        actor_id=ActorId(keys.CHECKER), bus=bus, inbox=Inbox(32), mode=mode
    )
    gate = GateActor(actor_id=ActorId(keys.GATE), bus=bus, inbox=Inbox(32))
    host = RunHost(
        actor_id=ActorId(keys.HOST),
        bus=bus,
        inbox=Inbox(32),
        job_factory=TickJob,
        workdir=workdir,
        goal_id=goal_id,
        goal_title="test goal",
        done_criteria=["hello.txt exists"],
        request_timeout=15.0,
    )

    async def work() -> TickJob:
        await bus.publish(
            make_envelope(
                topic=topics.RUN_START,
                payload={"args": {"tick": tick, "goal_id": goal_id}},
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
async def test_fake_tick_admit_writes_loop_artifacts(tmp_path: Path) -> None:
    job = await _one_tick(tmp_path, mode="admit")
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


@pytest.mark.asyncio
async def test_fake_tick_repair_rolls_back_world(tmp_path: Path) -> None:
    # Pre-existing file that must survive rollback of hello.txt apply
    (tmp_path / "keep.txt").write_text("keep\n", encoding="utf-8")
    job = await _one_tick(tmp_path, mode="repair_integrity")
    assert job.outcome and job.outcome["ok"] is True
    assert job.decision and job.decision["decision"] == "repair"
    assert job.decision["reason"] == "integrity_violation"

    assert not (tmp_path / "hello.txt").exists()
    assert (tmp_path / "keep.txt").read_text(encoding="utf-8") == "keep\n"

    loop_dir = paths.loop_goal_dir(tmp_path, "g-test")
    tree = loop_store.load_tree(loop_dir)
    assert tree is not None
    # repair → pending then ensure_pointer → in_progress again
    assert tree.root.status == "in_progress"
    assert tree.root.repair_streak == 1
    assert (loop_dir / "decisions" / "000.json").is_file()
