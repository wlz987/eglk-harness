"""Shared actor wiring for integration tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

from eba import ActorId, Bus, Inbox, make_envelope, run_actors

from eglk_harness.actors.checker import CheckerActor
from eglk_harness.actors.gate import GateActor
from eglk_harness.actors.governor import GovernorActor
from eglk_harness.actors.host import RunHost
from eglk_harness.actors.maker import MakerActor
from eglk_harness.actors.refiner import RefinerActor
from eglk_harness.actors.swarm import ExplorerActor, PrunerActor, VerifierActor
from eglk_harness.actors.tick import TickJob
from eglk_harness.domain.adapters import MockAdapter
from eglk_harness.domain.init_project import init_project
from eglk_harness.protocol import keys, topics


async def run_tick(
    workdir: Path,
    *,
    goal_id: str = "g-test",
    mode: str = "admit",
    swarm_soft: str | None = "0",
    uncertainty: float = 0.0,
    focus_score: float = 1.0,
) -> TickJob:
    init_project(workdir)
    adapter = MockAdapter(mode=mode)
    bus = Bus()

    def inbox() -> Inbox:
        return Inbox(32)

    actors = [
        MakerActor(
            actor_id=ActorId(keys.MAKER),
            bus=bus,
            inbox=inbox(),
            adapter=adapter,
            workdir=workdir,
            tools_allowed=True,
        ),
        CheckerActor(
            actor_id=ActorId(keys.CHECKER),
            bus=bus,
            inbox=inbox(),
            adapter=adapter,
            workdir=workdir,
            tools_allowed=True,
        ),
        GateActor(actor_id=ActorId(keys.GATE), bus=bus, inbox=inbox()),
        GovernorActor(actor_id=ActorId(keys.GOVERNOR), bus=bus, inbox=inbox(), workdir=workdir),
        ExplorerActor(actor_id=ActorId(keys.EXPLORER), bus=bus, inbox=inbox()),
        VerifierActor(actor_id=ActorId(keys.VERIFIER), bus=bus, inbox=inbox()),
        PrunerActor(actor_id=ActorId(keys.PRUNER), bus=bus, inbox=inbox()),
        RefinerActor(actor_id=ActorId(keys.REFINER), bus=bus, inbox=inbox()),
    ]
    host = RunHost(
        actor_id=ActorId(keys.HOST),
        bus=bus,
        inbox=inbox(),
        job_factory=TickJob,
        workdir=workdir,
        goal_id=goal_id,
        goal_title="test goal",
        done_criteria=["hello.txt exists"],
        swarm_soft=swarm_soft,
        focus_score=focus_score,
        uncertainty=uncertainty,
        request_timeout=20.0,
    )
    actors.append(host)

    async def work() -> TickJob:
        await bus.publish(
            make_envelope(
                topic=topics.RUN_START,
                payload={
                    "args": {
                        "tick": 0,
                        "goal_id": goal_id,
                        "swarm_soft": swarm_soft,
                        "focus_score": focus_score,
                        "uncertainty": uncertainty,
                    }
                },
                sender=ActorId("test"),
            )
        )
        async with asyncio.timeout(20):
            while not (host.jobs and host.jobs[0].finished):
                await asyncio.sleep(0.005)
        job = host.jobs[0]
        assert isinstance(job, TickJob)
        return job

    return await run_actors(actors, work, grace=1.0)
