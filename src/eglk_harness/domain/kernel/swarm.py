"""SWARM enablement (Phase 0 / Phase 2) — thresholds never abort."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from eglk_harness.domain.kernel import projections as P


@dataclass(frozen=True)
class SwarmPlan:
    explorer: bool
    verifier: bool
    pruner: bool
    reasons: tuple[str, ...] = ()

    def any_enabled(self) -> bool:
        return self.explorer or self.verifier or self.pruner

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_swarm(
    *,
    focus_score: float = 1.0,
    uncertainty: float = 0.0,
    candidate_count: int = 0,
    cognitive_tokens: int = 0,
    cognitive_tokens_max: int = P.COGNITIVE_TOKENS_MAX,
    soft: str | None = None,
) -> SwarmPlan:
    """Phase 0 Explorer/Verifier/Pruner enablement (no Governor/Refiner).

    ``soft``: ``\"0\"`` force off · ``\"1\"`` force at least Explorer · else auto.
    ``τ_focus`` / budget floor throttle only — never abort the run.
    """
    reasons: list[str] = []
    if soft == "0":
        return SwarmPlan(False, False, False, ("soft_off",))

    remaining = 1.0
    if cognitive_tokens_max > 0:
        remaining = max(0.0, 1.0 - (cognitive_tokens / cognitive_tokens_max))

    if remaining < P.SWARM_BUDGET_FLOOR:
        return SwarmPlan(False, False, False, ("budget_floor",))

    if focus_score < P.TAU_FOCUS and soft != "1":
        return SwarmPlan(False, False, False, ("focus_throttled",))

    explorer = True
    reasons.append("default_explorer")
    verifier = False
    pruner = False

    if uncertainty > P.TAU_UNC_HIGH:
        verifier = True
        reasons.append("uncertainty_high")
    if candidate_count > P.CANDIDATES_MAX:
        pruner = True
        reasons.append("candidates_overflow")
    if soft == "1":
        reasons.append("soft_on")

    return SwarmPlan(explorer, verifier, pruner, tuple(reasons))


def decide_refiner(
    *,
    decision: str,
    active_len: int = 0,
    focus_score: float = 1.0,
) -> bool:
    """Whether Phase 2 Refiner should run (not part of run_swarm)."""
    if decision == "repair":
        return True
    if decision == "abort":
        return True
    if active_len > P.SIGMA_ACTIVE_MAX:
        return True
    if decision == "admit" and focus_score < P.TAU_FOCUS:
        return False
    return decision in {"admit", "repair", "abort"}


def should_veto_after_admit(evidence: Mapping[str, Any] | None) -> bool:
    """Fix B: skip reopen when audit complete with ≥1 artifact."""
    if not evidence:
        return True
    try:
        audit = float(evidence.get("audit_progress", 0) or 0)
    except (TypeError, ValueError):
        audit = 0.0
    arts = evidence.get("artifacts") or []
    if not isinstance(arts, list):
        arts = []
    grounded = [a for a in arts if isinstance(a, str) and a.strip()]
    if audit >= P.TAU_DONE and len(grounded) >= 1:
        return False
    return True
