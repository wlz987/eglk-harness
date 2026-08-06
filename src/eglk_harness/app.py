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
from eglk_harness.domain.loop_store import load_tree, read_json
from eglk_harness.domain.manifest import build_manifest, new_run_id, write_manifest
from eglk_harness.domain.models import resolve_model
from eglk_harness.domain import paths
from eglk_harness.domain import projections as P
from eglk_harness.domain.init_project import init_project
from eglk_harness.protocol import keys, topics

_MOCK_TIMEOUT_S = 30.0
_LIVE_TIMEOUT_S = 600.0
# Soft safety only — never replaces cognitive_tokens / repairs_max as abort authority.
_DEFAULT_MAX_TICKS_SOFT = 32


@dataclass
class RunRequest:
    workdir: Path
    goal: str | None = None
    agent: str = "mock"
    swarm: str | None = None
    mcp_config: Path | None = None
    mcp_add_dirs: list[str] = field(default_factory=list)
    fake_mode: str = "admit"
    tick: int | None = None  # None → auto-resume from state.json
    compile: str | None = None
    focus_score: float = 1.0
    uncertainty: float = 0.0
    max_ticks: int = _DEFAULT_MAX_TICKS_SOFT


def _request_timeout(agent: str) -> float:
    return _MOCK_TIMEOUT_S if agent in {"mock", "fake"} else _LIVE_TIMEOUT_S


def resolve_start_tick(workdir: Path, goal_id_str: str, explicit: int | None) -> int:
    """Resume after the last completed tick when ``state.json`` exists.

    Explicit ``--tick`` always wins. Otherwise start at ``state.tick + 1`` so a
    failed tick can retry without rewriting earlier claim/evidence artifacts.
    """
    if explicit is not None:
        return max(0, int(explicit))
    state_path = paths.loop_goal_dir(workdir, goal_id_str) / "state.json"
    if not state_path.is_file():
        return 0
    try:
        data = read_json(state_path)
    except (OSError, ValueError):
        return 0
    if not isinstance(data, dict):
        return 0
    try:
        last = int(data.get("tick", -1))
    except (TypeError, ValueError):
        return 0
    if last < 0:
        return 0
    tree = load_tree(paths.loop_goal_dir(workdir, goal_id_str))
    if tree is not None and tree.all_work_admitted():
        return last
    return last + 1


def _should_continue(job: TickJob) -> bool:
    """Continue when work remains after admit, or Gate asked for repair retry."""
    decision = job.decision or {}
    kind = str(decision.get("decision") or "")
    answer = (job.outcome or {}).get("answer") if isinstance(job.outcome, dict) else {}
    if not isinstance(answer, dict):
        answer = {}
    if kind == "abort":
        return False
    if kind == "admit":
        return not bool(answer.get("root_done"))
    if kind == "repair":
        return bool(decision.get("should_run_next", True))
    # stage failure / unknown
    if job.outcome and job.outcome.get("ok") is False:
        return False
    return False


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


async def _await_job(host: RunHost, *, index: int, timeout_s: float) -> TickJob:
    async with asyncio.timeout(timeout_s):
        while len(host.jobs) <= index or not getattr(host.jobs[index], "finished", False):
            await asyncio.sleep(0.005)
    job = host.jobs[index]
    assert isinstance(job, TickJob)
    return job


async def _run_loop(request: RunRequest) -> dict[str, Any]:
    workdir = request.workdir.resolve()
    if not paths.harness_root(workdir).is_dir():
        init_project(workdir)

    backend = "mock" if request.agent in {"mock", "fake"} else request.agent
    compiled = compile_goal(workdir, mode=request.compile, backend=backend)
    if compiled.action == "error":
        raise RuntimeError(f"STEP0 compile failed: {compiled.detail}")

    bus, actors, host, gid, title, criteria = _assemble_actors(request, workdir)
    max_ticks = max(1, int(request.max_ticks or _DEFAULT_MAX_TICKS_SOFT))
    per_tick_timeout = _request_timeout(request.agent)
    start_tick = resolve_start_tick(workdir, gid, request.tick)

    async def work() -> dict[str, Any]:
        tick = int(start_tick)
        decisions: list[dict[str, Any]] = []
        written_all: list[str] = []
        last_job: TickJob | None = None
        stop_reason = "completed"

        for i in range(max_ticks):
            await bus.publish(
                make_envelope(
                    topic=topics.RUN_START,
                    payload={
                        "args": {
                            "tick": tick,
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
            last_job = await _await_job(host, index=i, timeout_s=per_tick_timeout)
            decision = last_job.decision if isinstance(last_job.decision, dict) else {}
            decisions.append(dict(decision))
            written_all.extend(list(last_job.written or []))

            if not _should_continue(last_job):
                kind = str(decision.get("decision") or "")
                answer = (last_job.outcome or {}).get("answer") if last_job.outcome else {}
                if kind == "admit" and isinstance(answer, dict) and answer.get("root_done"):
                    stop_reason = "root_admitted"
                elif kind == "abort":
                    stop_reason = f"abort:{decision.get('reason')}"
                elif last_job.outcome and last_job.outcome.get("ok") is False:
                    stop_reason = f"error:{last_job.outcome.get('error')}"
                else:
                    stop_reason = "halt"
                break
            tick += 1
        else:
            stop_reason = "max_ticks_soft"

        last_decision = decisions[-1] if decisions else {}
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
                decision=last_decision,
                extra={
                    "ticks_run": len(decisions),
                    "start_tick": start_tick,
                    "max_ticks_soft": max_ticks,
                    "stop_reason": stop_reason,
                    "budget_note": (
                        "max_ticks_soft is safety only; abort authority remains "
                        f"cognitive_tokens_max={P.COGNITIVE_TOKENS_MAX} + "
                        f"repairs_max={P.REPAIRS_MAX}"
                    ),
                },
            ),
        )
        outcome = last_job.outcome if last_job else {}
        return {
            "goal_id": gid,
            "outcome": outcome,
            "decision": last_decision or None,
            "decisions": decisions,
            "ticks_run": len(decisions),
            "start_tick": start_tick,
            "stop_reason": stop_reason,
            "written": written_all,
            "agent": request.agent,
            "compile": compiled.action,
            "swarm_plan": getattr(last_job, "swarm_plan", None) if last_job else None,
            "manifest": str(manifest_path),
            "integrity_mutations": list(getattr(last_job, "integrity_mutations", []) or [])
            if last_job
            else [],
        }

    return await run_actors(actors, work, grace=1.0)


def run(request: RunRequest) -> int:
    """STEP 0 compile → multi-tick four-phase loop → Manifest."""
    workdir = request.workdir.resolve()
    if not paths.goal_path(workdir).is_file() and not request.goal:
        print("error: missing .goal.md — run `eglk-harness init` or pass --goal", flush=True)
        return 2

    try:
        result = asyncio.run(_run_loop(request))
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
        f"  ticks={result.get('ticks_run')} start_tick={result.get('start_tick')} "
        f"stop={result.get('stop_reason')}\n"
        f"  swarm={swarm_s}\n"
        f"  decision={decision.get('decision')} ({decision.get('reason')})\n"
        f"  written={result.get('written')}\n"
        f"  manifest={result.get('manifest')}\n"
        f"  ok={outcome.get('ok')}",
        flush=True,
    )
    if outcome.get("ok") is False and decision.get("decision") != "repair":
        return 1
    if result.get("stop_reason", "").startswith("abort"):
        return 1
    return 0
