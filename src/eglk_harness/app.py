"""Composition root: the only module allowed to import actor families."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eba import ActorId, Bus, Inbox, make_envelope, run_actors

from eglk_harness.actors.checker import CheckerActor
from eglk_harness.actors.gate import GateActor
from eglk_harness.actors.host import RunHost
from eglk_harness.actors.maker import MakerActor
from eglk_harness.actors.tick import TickJob
from eglk_harness.domain.adapters import create_adapter
from eglk_harness.domain.adapters.mcp import assert_tools_for_role, resolve_add_dirs, resolve_mcp_config
from eglk_harness.domain import paths
from eglk_harness.domain.init_project import init_project
from eglk_harness.protocol import keys, topics


@dataclass
class RunRequest:
    workdir: Path
    goal: str | None = None
    agent: str = "mock"  # mock | codex | claude_code — live backends need binaries
    swarm: str | None = None
    mcp_config: Path | None = None
    mcp_add_dirs: list[str] = field(default_factory=list)
    fake_mode: str = "admit"
    tick: int = 0


def _goal_text(request: RunRequest, workdir: Path) -> str:
    if request.goal:
        p = Path(request.goal)
        if p.is_file():
            return p.read_text(encoding="utf-8")
        return request.goal
    goal_file = paths.goal_path(workdir)
    return goal_file.read_text(encoding="utf-8")


def _goal_id(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"g-{digest}"


def _title_from_goal(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip() or "goal"
    return "goal"


def _done_criteria(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^[-*]\s*\[[ xX]?\]\s*(.+)$", line.strip())
        if m:
            items.append(m.group(1).strip())
    return items or ["hello.txt exists"]


def _assemble_actors(
    request: RunRequest, workdir: Path
) -> tuple[Bus, list[Any], RunHost, str, str, list[str]]:
    """Build maker/checker/gate/host. MCP only on Maker/Checker."""
    text = _goal_text(request, workdir)
    goal_id = _goal_id(text)
    title = _title_from_goal(text)
    criteria = _done_criteria(text)

    mcp_path = resolve_mcp_config(request.mcp_config)
    add_dirs = resolve_add_dirs(request.mcp_add_dirs)

    # Trust boundary: only tool roles may see MCP
    assert_tools_for_role("maker", tools_allowed=True)
    assert_tools_for_role("checker", tools_allowed=True)

    adapter = create_adapter(
        request.agent,
        mcp_config=mcp_path,
        add_dirs=add_dirs,
        mock_mode=request.fake_mode,
    )

    bus = Bus()
    maker = MakerActor(
        actor_id=ActorId(keys.MAKER),
        bus=bus,
        inbox=Inbox(32),
        adapter=adapter,
        workdir=workdir,
        tools_allowed=True,
        mcp_config=mcp_path,
        add_dirs=add_dirs,
    )
    checker = CheckerActor(
        actor_id=ActorId(keys.CHECKER),
        bus=bus,
        inbox=Inbox(32),
        adapter=adapter,
        workdir=workdir,
        tools_allowed=True,
        mcp_config=mcp_path,
        add_dirs=add_dirs,
    )
    gate = GateActor(actor_id=ActorId(keys.GATE), bus=bus, inbox=Inbox(32))
    host = RunHost(
        actor_id=ActorId(keys.HOST),
        bus=bus,
        inbox=Inbox(32),
        job_factory=TickJob,
        workdir=workdir,
        goal_id=goal_id,
        goal_title=title,
        done_criteria=criteria,
        request_timeout=30.0 if request.agent == "mock" else 600.0,
    )
    return bus, [maker, checker, gate, host], host, goal_id, title, criteria


async def _run_one_tick(request: RunRequest) -> dict[str, Any]:
    workdir = request.workdir.resolve()
    if not paths.harness_root(workdir).is_dir():
        init_project(workdir)

    bus, actors, host, goal_id, title, criteria = _assemble_actors(request, workdir)

    async def work() -> dict[str, Any]:
        await bus.publish(
            make_envelope(
                topic=topics.RUN_START,
                payload={
                    "args": {
                        "tick": request.tick,
                        "goal_id": goal_id,
                        "goal_title": title,
                        "done_criteria": criteria,
                    }
                },
                sender=ActorId("cli"),
            )
        )
        timeout = 30.0 if request.agent == "mock" else 600.0
        async with asyncio.timeout(timeout):
            while not (host.jobs and getattr(host.jobs[0], "finished", False)):
                await asyncio.sleep(0.005)
        job = host.jobs[0]
        outcome = getattr(job, "outcome", None) or {}
        return {
            "goal_id": goal_id,
            "outcome": outcome,
            "decision": getattr(job, "decision", None),
            "written": list(getattr(job, "written", []) or []),
            "agent": request.agent,
        }

    return await run_actors(actors, work, grace=1.0)


def run(request: RunRequest) -> int:
    """Start a harness run (M3: Adapter-backed Maker/Checker; default mock)."""
    workdir = request.workdir.resolve()
    goal_file = paths.goal_path(workdir)
    if not goal_file.is_file() and not request.goal:
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
    print(
        "eglk-harness run\n"
        f"  workdir={workdir}\n"
        f"  agent={result.get('agent')}\n"
        f"  goal_id={result.get('goal_id')}\n"
        f"  decision={decision.get('decision')} ({decision.get('reason')})\n"
        f"  written={result.get('written')}\n"
        f"  ok={outcome.get('ok')}",
        flush=True,
    )
    if outcome.get("ok") is False and decision.get("decision") != "repair":
        return 1
    return 0
