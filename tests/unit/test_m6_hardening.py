"""Hardening: integrity monitor, projections CI, Manifest, model resolve."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from eba import ActorId, Bus, Inbox, make_envelope, run_actors

from eglk_harness.actors.checker import CheckerActor
from eglk_harness.actors.gate import GateActor
from eglk_harness.actors.governor import GovernorActor
from eglk_harness.actors.host import RunHost
from eglk_harness.actors.maker import MakerActor
from eglk_harness.actors.refiner import RefinerActor
from eglk_harness.actors.swarm import ExplorerActor, PrunerActor, VerifierActor
from eglk_harness.actors.tick import TickJob
from eglk_harness.cli import main
from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.adapters import MockAdapter
from eglk_harness.domain.product.check_projections import EXPECTED, check_projections
from eglk_harness.domain.kernel.integrity import apply_integrity_flag, fingerprint_workdir
from eglk_harness.domain.product.init_project import init_project
from eglk_harness.domain.product.manifest import build_manifest, local_runs_root, write_manifest
from eglk_harness.domain.runtime.models import NEVER_DOWNGRADE_ROLES, may_downgrade, resolve_model
from eglk_harness.protocol import keys, topics, payload as pl


def test_check_projections_ok() -> None:
    report = check_projections()
    assert report.ok, [c for c in report.checks if not c.ok]
    assert EXPECTED["TAU_DONE"] == P.TAU_DONE


def test_fingerprint_detects_write(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("1\n", encoding="utf-8")
    before = fingerprint_workdir(tmp_path)
    (tmp_path / "a.txt").write_text("2\n", encoding="utf-8")
    after = fingerprint_workdir(tmp_path)
    evidence: dict = {"gaps": [], "integrity_violation": False}
    muts = apply_integrity_flag(evidence, before=before, after=after)
    assert muts == ["a.txt"]
    assert evidence["integrity_violation"] is True


@pytest.mark.asyncio
async def test_integrity_forces_repair(tmp_path: Path) -> None:
    class MutatingChecker(CheckerActor):
        async def work(self, body):  # type: ignore[no-untyped-def]
            args = pl.get_args(body if isinstance(body, dict) else {})
            wd = Path(str(args.get("workdir") or tmp_path))
            (wd / "evil.txt").write_text("checker wrote me\n", encoding="utf-8")
            return await super().work(body)

    init_project(tmp_path)
    adapter = MockAdapter(mode="admit")
    bus = Bus()
    inbox = lambda: Inbox(32)  # noqa: E731
    actors = [
        MakerActor(
            actor_id=ActorId(keys.MAKER),
            bus=bus,
            inbox=inbox(),
            adapter=adapter,
            workdir=tmp_path,
            tools_allowed=True,
        ),
        MutatingChecker(
            actor_id=ActorId(keys.CHECKER),
            bus=bus,
            inbox=inbox(),
            adapter=adapter,
            workdir=tmp_path,
            tools_allowed=True,
        ),
        GateActor(actor_id=ActorId(keys.GATE), bus=bus, inbox=inbox()),
        GovernorActor(actor_id=ActorId(keys.GOVERNOR), bus=bus, inbox=inbox(), workdir=tmp_path),
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
        workdir=tmp_path,
        goal_id="g-int",
        swarm_soft="0",
        request_timeout=20.0,
    )
    actors.append(host)

    async def work():
        await bus.publish(
            make_envelope(
                topic=topics.RUN_START,
                payload={"args": {"tick": 0, "goal_id": "g-int", "swarm_soft": "0"}},
                sender=ActorId("t"),
            )
        )
        async with asyncio.timeout(20):
            while not (host.jobs and host.jobs[0].finished):
                await asyncio.sleep(0.005)
        return host.jobs[0]

    job = await run_actors(actors, work, grace=1.0)
    assert job.decision and job.decision["decision"] == "repair"
    assert job.decision["reason"] == "integrity_violation"
    assert job.integrity_mutations


def test_manifest_write(tmp_path: Path) -> None:
    m = build_manifest(
        run_id="testrun",
        workdir=tmp_path,
        goal_id="g1",
        agent="mock",
        decision={"decision": "admit", "reason": "consistent_completion"},
    )
    path = write_manifest(tmp_path, m)
    assert path.is_file()
    assert "schema_version" in path.read_text(encoding="utf-8")
    assert (local_runs_root(tmp_path) / "testrun" / "manifest.json").is_file()


def test_model_resolve_shared_and_never_downgrade() -> None:
    assert resolve_model("maker", env={"EGLK_MODEL": "shared"}) == "shared"
    assert (
        resolve_model("explorer", env={"EGLK_MODEL_EXPLORER": "cheap", "EGLK_MODEL": "shared"})
        == "cheap"
    )
    assert may_downgrade("verifier") is True
    assert may_downgrade("maker") is False
    assert NEVER_DOWNGRADE_ROLES == frozenset({"maker", "governor", "checker"})


def test_cli_check_projections() -> None:
    with pytest.raises(SystemExit) as ei:
        main(["check-projections"])
    assert ei.value.code == 0
