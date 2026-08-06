"""M4: four-phase tick — SWARM candidates never enter Gate; refined merges in Phase 3."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eglk_harness.domain import paths, sigma
from eglk_harness.domain.init_project import init_project
from helpers.tick_runtime import run_tick


@pytest.mark.asyncio
async def test_phase0_swarm_then_gate_without_candidates(tmp_path: Path) -> None:
    job = await run_tick(
        tmp_path,
        goal_id="g-m4",
        mode="admit",
        swarm_soft="1",
        uncertainty=0.9,  # also enable verifier
        use_fake=True,
    )
    assert job.decision and job.decision["decision"] == "admit"
    assert job.swarm_plan and job.swarm_plan.explorer is True
    assert job.swarm_plan.verifier is True
    # Gate payload must not include candidates / sigma
    keys = set(job.gate_payload_keys or ())
    assert keys == {"claim", "evidence", "quota", "repair_counts"}
    assert "candidates" not in keys

    loop = paths.loop_goal_dir(tmp_path, "g-m4")
    # Phase 3 archived explorer (file cleared)
    assert not (loop / "candidates" / "explorer_000.json").exists()
    assert (loop / "reasoning_log.jsonl").is_file()
    assert (loop / "ticks.jsonl").is_file()
    # Σ merged into memory authority
    active = sigma.load_active(tmp_path)
    assert any(x.get("kind") == "hit" for x in active)
    assert sigma.list_refined(loop) == []


@pytest.mark.asyncio
async def test_refined_does_not_pollute_same_tick_before_phase3(tmp_path: Path) -> None:
    """Sanity: write_refined alone does not touch memory until phase3 merge (unit-covered);
    full tick ends with merge complete and staging empty.
    """
    init_project(tmp_path)
    job = await run_tick(tmp_path, goal_id="g-m4b", mode="admit", swarm_soft="0")
    assert job.outcome and job.outcome.get("ok") is True
    answer = (job.outcome or {}).get("answer") or {}
    assert answer.get("refined_staged_before_phase3", 0) >= 1
    loop = paths.loop_goal_dir(tmp_path, "g-m4b")
    assert sigma.list_refined(loop) == []
    assert sigma.load_active(tmp_path)


@pytest.mark.asyncio
async def test_veto_skipped_when_fix_b(tmp_path: Path) -> None:
    job = await run_tick(tmp_path, goal_id="g-m4c", mode="admit", swarm_soft="0")
    # Mock admit evidence has audit=1 and artifacts → no veto file leftover
    loop = paths.loop_goal_dir(tmp_path, "g-m4c")
    assert not (loop / "candidates" / "verifier_audit_000.json").exists()
    # reasoning log may still have leaf_contract archive
    assert job.decision["decision"] == "admit"


def test_swarm_actor_rejects_mcp() -> None:
    from eba import ActorId, Bus, Inbox
    from eglk_harness.actors.swarm import ExplorerActor

    with pytest.raises(AssertionError):
        ExplorerActor(
            actor_id=ActorId("x"),
            bus=Bus(),
            inbox=Inbox(4),
            tools_allowed=True,
        )
