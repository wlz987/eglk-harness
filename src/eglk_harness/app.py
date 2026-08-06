"""Composition root: the only module allowed to import actor families."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eba import ActorId, Bus, Inbox, make_envelope, run_actors

from eglk_harness.actors.checker import CheckerActor
from eglk_harness.actors.gate import GateActor
from eglk_harness.actors.governor import GovernorActor
from eglk_harness.actors.host import RunHost
from eglk_harness.actors.maker import MakerActor
from eglk_harness.actors.refiner import RefinerActor
from eglk_harness.actors.swarm import ExplorerActor, PrunerActor, VerifierActor
from eglk_harness.actors.tick import TickJob
from eglk_harness.domain.adapters import create_adapter
from eglk_harness.domain.adapters.mcp import assert_tools_for_role, resolve_add_dirs, resolve_mcp_config
from eglk_harness.domain.compile_goal import compile_goal
from eglk_harness.domain.goal_parse import done_criteria, goal_id, read_goal_text, title_from_goal
from eglk_harness.domain.manifest import build_manifest, new_run_id, write_manifest
from eglk_harness.domain.models import resolve_model
from eglk_harness.domain import paths
from eglk_harness.domain.init_project import init_project
from eglk_harness.protocol import keys, topics

_MOCK_TIMEOUT_S = 30.0
_LIVE_TIMEOUT_S = 600.0


@dataclass
class RunRequest:
    workdir: Path
    goal: str | None = None
    agent: str = "mock"
    swarm: str | None = None
    mcp_config: Path | None = None
    mcp_add_dirs: list[str] = field(default_factory=list)
    fake_mode: str = "admit"
    tick: int = 0
    compile: str | None = None
    focus_score: float = 1.0
    uncertainty: float = 0.0


def _request_timeout(agent: str) -> float:
    return _MOCK_TIMEOUT_S if agent in {"mock", "fake"} else _LIVE_TIMEOUT_S


def _assemble_actors(
    request: RunRequest, workdir: Path
) -> tuple[Bus, list[Any], RunHost, str, str, list[str]]:
    text = read_goal_text(workdir, request.goal)
    gid = goal_id(text)
    title = title_from_goal(text)
    criteria = done_criteria(text)

    mcp_path = resolve_mcp_config(request.mcp_config)
    add_dirs = resolve_add_dirs(request.mcp_add_dirs)

    for role, allowed in (
        ("maker", True),
        ("checker", True),
        ("governor", False),
        ("explorer", False),
        ("refiner", False),
    ):
        assert_tools_for_role(role, tools_allowed=allowed)

    adapter = create_adapter(
        request.agent,
        mcp_config=mcp_path,
        add_dirs=add_dirs,
        mock_mode=request.fake_mode,
    )

    bus = Bus()

    def _inbox() -> Inbox:
        return Inbox(32)

    tool_kw = dict(
        adapter=adapter,
        workdir=workdir,
        tools_allowed=True,
        mcp_config=mcp_path,
        add_dirs=add_dirs,
    )
    actors: list[Any] = [
        MakerActor(actor_id=ActorId(keys.MAKER), bus=bus, inbox=_inbox(), **tool_kw),
        CheckerActor(actor_id=ActorId(keys.CHECKER), bus=bus, inbox=_inbox(), **tool_kw),
        GateActor(actor_id=ActorId(keys.GATE), bus=bus, inbox=_inbox()),
        GovernorActor(
            actor_id=ActorId(keys.GOVERNOR), bus=bus, inbox=_inbox(), workdir=workdir
        ),
        ExplorerActor(actor_id=ActorId(keys.EXPLORER), bus=bus, inbox=_inbox()),
        VerifierActor(actor_id=ActorId(keys.VERIFIER), bus=bus, inbox=_inbox()),
        PrunerActor(actor_id=ActorId(keys.PRUNER), bus=bus, inbox=_inbox()),
        RefinerActor(actor_id=ActorId(keys.REFINER), bus=bus, inbox=_inbox()),
    ]
    host = RunHost(
        actor_id=ActorId(keys.HOST),
        bus=bus,
        inbox=_inbox(),
        job_factory=TickJob,
        workdir=workdir,
        goal_id=gid,
        goal_title=title,
        done_criteria=criteria,
        swarm_soft=request.swarm,
        focus_score=request.focus_score,
        uncertainty=request.uncertainty,
        request_timeout=_request_timeout(request.agent),
    )
    actors.append(host)
    return bus, actors, host, gid, title, criteria


async def _run_one_tick(request: RunRequest) -> dict[str, Any]:
    workdir = request.workdir.resolve()
    if not paths.harness_root(workdir).is_dir():
        init_project(workdir)

    backend = "mock" if request.agent in {"mock", "fake"} else request.agent
    compiled = compile_goal(workdir, mode=request.compile, backend=backend)
    if compiled.action == "error":
        raise RuntimeError(f"STEP0 compile failed: {compiled.detail}")

    bus, actors, host, gid, title, criteria = _assemble_actors(request, workdir)

    async def work() -> dict[str, Any]:
        await bus.publish(
            make_envelope(
                topic=topics.RUN_START,
                payload={
                    "args": {
                        "tick": request.tick,
                        "goal_id": gid,
                        "goal_title": title,
                        "done_criteria": criteria,
                        "swarm_soft": request.swarm,
                        "focus_score": request.focus_score,
                        "uncertainty": request.uncertainty,
                    }
                },
                sender=ActorId("cli"),
            )
        )
        async with asyncio.timeout(_request_timeout(request.agent)):
            while not (host.jobs and getattr(host.jobs[0], "finished", False)):
                await asyncio.sleep(0.005)
        job = host.jobs[0]
        outcome = getattr(job, "outcome", None) or {}
        decision = getattr(job, "decision", None) or {}
        manifest_path = write_manifest(
            workdir,
            build_manifest(
                run_id=new_run_id(),
                workdir=workdir,
                goal_id=gid,
                agent=request.agent,
                model=resolve_model("maker"),
                mcp_config=request.mcp_config,
                swarm=request.swarm,
                decision=decision if isinstance(decision, dict) else {},
            ),
        )
        return {
            "goal_id": gid,
            "outcome": outcome,
            "decision": decision if isinstance(decision, dict) else None,
            "written": list(getattr(job, "written", []) or []),
            "agent": request.agent,
            "compile": compiled.action,
            "swarm_plan": getattr(job, "swarm_plan", None),
            "manifest": str(manifest_path),
            "integrity_mutations": list(getattr(job, "integrity_mutations", []) or []),
        }

    return await run_actors(actors, work, grace=1.0)


def run(request: RunRequest) -> int:
    """Run one tick: STEP 0 compile → four phases → Manifest."""
    workdir = request.workdir.resolve()
    if not paths.goal_path(workdir).is_file() and not request.goal:
        print("error: missing .goal.md — run `eglk-harness init` or pass --goal", flush=True)
        return 2

    try:
        result = asyncio.run(_run_one_tick(request))
    except TimeoutError:
        print("error: tick timed out", flush=True)
        return 1
    except AssertionError as exc:
        print(f"error: assembly rejected — {exc}", flush=True)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", flush=True)
        return 1

    outcome = result.get("outcome") or {}
    decision = result.get("decision") or {}
    swarm = result.get("swarm_plan")
    swarm_s = swarm.to_dict() if swarm is not None and hasattr(swarm, "to_dict") else swarm
    print(
        "eglk-harness run\n"
        f"  workdir={workdir}\n"
        f"  agent={result.get('agent')}\n"
        f"  compile={result.get('compile')}\n"
        f"  goal_id={result.get('goal_id')}\n"
        f"  swarm={swarm_s}\n"
        f"  decision={decision.get('decision')} ({decision.get('reason')})\n"
        f"  written={result.get('written')}\n"
        f"  manifest={result.get('manifest')}\n"
        f"  ok={outcome.get('ok')}",
        flush=True,
    )
    if outcome.get("ok") is False and decision.get("decision") != "repair":
        return 1
    return 0
