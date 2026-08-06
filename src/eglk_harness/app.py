"""Composition root: the only module allowed to import actor families."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunRequest:
    workdir: Path
    goal: str | None = None
    agent: str = "codex"
    swarm: str | None = None
    mcp_config: Path | None = None


def run(request: RunRequest) -> int:
    """Start a harness run.

    M0: scaffolding only — actors / eba wiring lands in M2.
    """
    workdir = request.workdir.resolve()
    goal_file = workdir / ".goal.md"
    if not goal_file.is_file() and not request.goal:
        print("error: missing .goal.md — run `eglk-harness init` or pass --goal", flush=True)
        return 2

    print(
        "eglk-harness run: runtime not wired yet (M0 stub).\n"
        f"  workdir={workdir}\n"
        f"  agent={request.agent}\n"
        f"  goal={request.goal or goal_file}\n"
        "Next: M1 domain gate/tree, then M2 actors+eba.",
        flush=True,
    )
    return 0
