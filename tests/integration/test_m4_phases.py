"""Four-phase tick: SWARM stays off Gate; refined merges only in Phase 3."""

from __future__ import annotations

from pathlib import Path

import pytest
from eba import ActorId, Bus, Inbox

from eglk_harness.actors.swarm import ExplorerActor
from eglk_harness.domain import paths, sigma
from eglk_harness.domain.init_project import init_project
from helpers.tick_runtime import run_tick


@pytest.mark.asyncio
async def test_phase0_swarm_then_gate_without_candidates(tmp_path: Path) -> None:
    job = await run_tick(
        tmp_path,
        goal_id="g-phase",
        mode="admit",
        swarm_soft="1",
        uncertainty=0.9,
    )
    assert job.decision and job.decision["decision"] == "admit"
    assert job.swarm_plan and job.swarm_plan.explorer is True
    assert job.swarm_plan.verifier is True
    assert set(job.gate_payload_keys or ()) == {"claim", "evidence", "quota", "repair_counts"}

    loop = paths.loop_goal_dir(tmp_path, "g-phase")
    assert not (loop / "candidates" / "explorer_000.json").exists()
    assert (loop / "reasoning_log.jsonl").is_file()
    assert (loop / "ticks.jsonl").is_file()
    assert any(x.get("kind") == "hit" for x in sigma.load_active(tmp_path))
    assert sigma.list_refined(loop) == []


@pytest.mark.asyncio
async def test_refined_merges_only_after_phase3(tmp_path: Path) -> None:
    init_project(tmp_path)
    job = await run_tick(tmp_path, goal_id="g-sigma", mode="admit", swarm_soft="0")
    assert job.outcome and job.outcome.get("ok") is True
    answer = (job.outcome or {}).get("answer") or {}
    assert answer.get("refined_staged_before_phase3", 0) >= 1
    loop = paths.loop_goal_dir(tmp_path, "g-sigma")
    assert sigma.list_refined(loop) == []
    assert sigma.load_active(tmp_path)


@pytest.mark.asyncio
async def test_veto_skipped_when_fully_grounded(tmp_path: Path) -> None:
    job = await run_tick(tmp_path, goal_id="g-veto", mode="admit", swarm_soft="0")
    loop = paths.loop_goal_dir(tmp_path, "g-veto")
    assert not (loop / "candidates" / "verifier_audit_000.json").exists()
    assert job.decision["decision"] == "admit"


def test_swarm_actor_rejects_mcp() -> None:
    with pytest.raises(AssertionError):
        ExplorerActor(
            actor_id=ActorId("x"),
            bus=Bus(),
            inbox=Inbox(4),
            tools_allowed=True,
        )
