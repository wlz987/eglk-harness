from __future__ import annotations

from typing import Any

from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.gate import decide


def _claim(**over: Any) -> dict[str, Any]:
    c: dict[str, Any] = {
        "claim_id": "c1",
        "tick": 0,
        "maker_session_id": "m1",
        "kind": "files",
        "done_progress": 1.0,
        "confidence": 0.9,
        "alternatives": [{"text": "alt", "status": "reject", "reason": "worse"}],
        "payload": {"files": {"a.txt": "ok"}},
        "step_review": {
            "gains": ["file written"],
            "losses": ["no broader refactor"],
            "benefits": ["leaf acceptance checkable"],
            "risks": ["content may be wrong"],
        },
        "shortcut_hit": False,
        "subgoal_id": "root",
    }
    c.update(over)
    return c


def _evidence(**over: Any) -> dict[str, Any]:
    e: dict[str, Any] = {
        "evidence_id": "e1",
        "tick": 0,
        "checker_session_id": "c1",
        "audit_progress": 1.0,
        "audit_confidence": 0.9,
        "gaps": [],
        "alternatives": [],
        "alternatives_missing": False,
        "challenges": [],
        "cost_usd": 0.0,
        "artifacts": ["a.txt observed"],
        "integrity_violation": False,
        "criteria_defect": False,
        "subgoal_id": "root",
    }
    e.update(over)
    return e


def test_projections_pin() -> None:
    assert P.TAU_DONE == 1.0
    assert P.TAU_GAP == 0.5
    assert P.REPAIRS_MAX == 8
    assert P.COGNITIVE_TOKENS_MAX == 64000
    assert P.SPLIT_REPAIR_STREAK == 2
    assert P.MAX_SPLIT_DEPTH == 4
    assert "tau_focus" in P.NON_ABORT_THRESHOLDS


def test_admit_consistent_completion() -> None:
    d = decide(_claim(), _evidence())
    assert d.decision == "admit"
    assert d.reason == "consistent_completion"
    assert d.should_run_next is False


def test_no_artifacts_never_admit() -> None:
    d = decide(_claim(), _evidence(artifacts=[]))
    assert d.decision == "repair"
    assert d.reason == "no_evidence_grounding"


def test_blank_artifacts_ignored() -> None:
    d = decide(_claim(), _evidence(artifacts=["", "  "]))
    assert d.decision == "repair"
    assert d.reason == "no_evidence_grounding"


def test_integrity_violation_repair() -> None:
    d = decide(_claim(), _evidence(integrity_violation=True))
    assert d.decision == "repair"
    assert d.reason == "integrity_violation"


def test_integrity_blocks_criteria_defect_admit() -> None:
    d = decide(
        _claim(),
        _evidence(integrity_violation=True, criteria_defect=True, gaps=["spec"]),
    )
    assert d.decision == "repair"
    assert d.reason == "integrity_violation"


def test_perception_gap() -> None:
    d = decide(_claim(done_progress=1.0), _evidence(audit_progress=0.4))
    assert d.decision == "repair"
    assert d.reason == "perception_gap"
    assert d.perception_gap == 0.6


def test_incomplete() -> None:
    d = decide(
        _claim(done_progress=0.5),
        _evidence(audit_progress=0.5, gaps=["missing"]),
    )
    assert d.decision == "repair"
    assert d.reason == "incomplete"


def test_challenges_merge_into_gaps_block_admit() -> None:
    d = decide(_claim(), _evidence(gaps=[], challenges=["unsure"]))
    assert d.decision == "repair"
    assert d.gaps_count == 1


def test_missing_alternatives() -> None:
    d = decide(_claim(alternatives=[]), _evidence())
    assert d.decision == "repair"
    assert d.reason == "missing_alternatives"


def test_shortcut_path_via_incomplete_when_under_tau_done() -> None:
    d = decide(
        _claim(shortcut_hit=True, done_progress=0.9),
        _evidence(audit_progress=0.9, gaps=[]),
    )
    assert d.decision == "repair"
    assert d.reason == "incomplete"


def test_criteria_defect_admit() -> None:
    d = decide(
        _claim(),
        _evidence(criteria_defect=True, gaps=["spec typo"], challenges=[]),
    )
    assert d.decision == "admit"
    assert d.reason == "criteria_defect_acknowledged"


def test_cognitive_budget_abort() -> None:
    d = decide(
        _claim(),
        _evidence(),
        quota={"cognitive_tokens": 64000, "cognitive_tokens_max": 64000},
    )
    assert d.decision == "abort"
    assert d.reason == "cognitive_budget"


def test_repairs_exhausted() -> None:
    d = decide(
        _claim(),
        _evidence(artifacts=[]),
        repair_counts={"no_evidence_grounding": P.REPAIRS_MAX},
    )
    assert d.decision == "abort"
    assert d.reason == "no_evidence_grounding_exhausted"


def test_commands_empty_payload() -> None:
    d = decide(
        _claim(kind="commands", payload={"commands": []}),
        _evidence(artifacts=["log"]),
    )
    assert d.reason == "no_evidence_grounding"


def test_tau_focus_unc_never_in_decision_reason() -> None:
    d = decide(_claim(), _evidence())
    assert "focus" not in d.reason
    assert d.reason != "tau_unc"
