"""Unit tests for SWARM / compile / sigma (M4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.domain import projections as P
from eglk_harness.domain import sigma
from eglk_harness.domain.compile_goal import compile_goal
from eglk_harness.domain.swarm import decide_refiner, decide_swarm, should_veto_after_admit


def test_decide_swarm_default_explorer() -> None:
    plan = decide_swarm()
    assert plan.explorer is True
    assert plan.verifier is False


def test_decide_swarm_soft_off() -> None:
    plan = decide_swarm(soft="0")
    assert plan.any_enabled() is False


def test_decide_swarm_focus_throttle() -> None:
    plan = decide_swarm(focus_score=P.TAU_FOCUS - 0.01)
    assert plan.any_enabled() is False
    assert "focus_throttled" in plan.reasons


def test_decide_swarm_uncertainty_verifier() -> None:
    plan = decide_swarm(uncertainty=P.TAU_UNC_HIGH + 0.1)
    assert plan.explorer and plan.verifier


def test_decide_swarm_budget_floor() -> None:
    plan = decide_swarm(cognitive_tokens=62000, cognitive_tokens_max=64000)
    assert plan.any_enabled() is False


def test_decide_refiner_repair_always() -> None:
    assert decide_refiner(decision="repair") is True


def test_veto_fix_b_exit() -> None:
    assert should_veto_after_admit({"audit_progress": 1.0, "artifacts": ["a.txt"]}) is False
    assert should_veto_after_admit({"audit_progress": 0.5, "artifacts": ["a.txt"]}) is True


def test_compile_auto_and_off(tmp_path: Path) -> None:
    (tmp_path / ".goal.md").write_text("# G\n\n- [ ] x\n", encoding="utf-8")
    r = compile_goal(tmp_path, mode="off", backend="mock")
    assert r.action == "skipped"
    r2 = compile_goal(tmp_path, mode="force", backend="mock")
    assert r2.action == "wrote"
    assert (tmp_path / ".goal_format.md").is_file()
    r3 = compile_goal(tmp_path, mode="auto", backend="mock")
    assert r3.action == "reused"


def test_compile_fails_without_backend(tmp_path: Path) -> None:
    (tmp_path / ".goal.md").write_text("# G\n", encoding="utf-8")
    r = compile_goal(tmp_path, mode="force", backend="codex", binary_present=False)
    assert r.action == "error"


def test_sigma_refined_merges_only_in_phase3(tmp_path: Path) -> None:
    from eglk_harness.domain.init_project import init_project
    from eglk_harness.domain import loop_store, paths

    init_project(tmp_path)
    loop = loop_store.ensure_loop_layout(tmp_path, "g1")
    assert sigma.load_active(tmp_path) == []
    sigma.write_refined(loop, 0, {"id": "s1", "text": "lesson", "conf": 0.5})
    # Still empty active before merge
    assert sigma.load_active(tmp_path) == []
    assert len(sigma.list_refined(loop)) == 1
    n = sigma.merge_refined_into_active(tmp_path, loop)
    assert n == 1
    assert len(sigma.load_active(tmp_path)) == 1
    assert sigma.list_refined(loop) == []
    # memory authority path
    assert paths.memory_sigma_dir(tmp_path).joinpath("active.json").is_file()
