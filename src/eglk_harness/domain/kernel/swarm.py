"""Advisor enablement — event-trigger thresholds never abort.

Replaces 0.2.x uncertainty/focus_score authority with observable candidate backlog
and budget floor. LLM Pruner → mechanical CandidateSelector.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from eglk_harness.domain.kernel import projections as P


@dataclass(frozen=True)
class SwarmPlan:
    explorer: bool
    verifier: bool
    candidate_selector: bool
    reasons: tuple[str, ...] = ()

    # Back-compat alias used by older tick code
    @property
    def pruner(self) -> bool:
        return self.candidate_selector

    def any_enabled(self) -> bool:
        return self.explorer or self.verifier or self.candidate_selector

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["pruner"] = self.candidate_selector
        return d


def decide_swarm(
    *,
    focus_score: float = 1.0,  # ignored (diagnostic only; kept for call-site compat)
    uncertainty: float = 0.0,  # ignored (diagnostic only)
    candidate_count: int = 0,
    cognitive_tokens: int = 0,
    cognitive_tokens_max: int = P.COGNITIVE_TOKENS_MAX,
    soft: str | None = None,
    last_repair_reason: str | None = None,
) -> SwarmPlan:
    """Explorer/Verifier/CandidateSelector enablement.

    ``soft``: ``\"0\"`` force off · ``\"1\"`` force at least Explorer · else auto.
    Budget floor throttles only — never aborts the run.
    """
    _ = (focus_score, uncertainty)  # explicitly non-authoritative
    reasons: list[str] = []
    if soft == "0":
        return SwarmPlan(False, False, False, ("soft_off",))

    remaining = 1.0
    if cognitive_tokens_max > 0:
        remaining = max(0.0, 1.0 - (cognitive_tokens / cognitive_tokens_max))

    if remaining < P.SWARM_BUDGET_FLOOR:
        return SwarmPlan(False, False, False, ("budget_floor",))

    explorer = True
    reasons.append("default_explorer")
    verifier = False
    selector = False

    repair_reason = (last_repair_reason or "").strip()
    if repair_reason in {
        "no_attestation",
        "boundary_unmet",
        "integrity_violation",
        "missing_alternatives",
        "capability_ceiling_exceeded",
    }:
        verifier = True
        reasons.append(f"repair_{repair_reason}")
    if candidate_count > P.CANDIDATES_MAX:
        selector = True
        verifier = True
        reasons.append("candidates_overflow")
    if soft == "1":
        reasons.append("soft_on")

    return SwarmPlan(explorer, verifier, selector, tuple(reasons))


def should_run_end_refiner(
    run_status: str,
    *,
    sigma_staging_count: int = 0,
) -> bool:
    """Refiner runs only after terminal run status (multi_agent §5.4)."""
    if run_status not in {"succeeded", "aborted", "invalid", "faulted"}:
        return False
    return sigma_staging_count > 0 or run_status in {"succeeded", "aborted", "invalid", "faulted"}


def decide_refiner(
    *,
    sigma_staging_count: int = 0,
    force: bool = False,
    decision: str = "",
    run_status: str = "",
) -> bool:
    """Deprecated per-tick hook — use ``should_run_end_refiner`` at run boundary."""
    _ = (decision, force)
    if run_status:
        return should_run_end_refiner(run_status, sigma_staging_count=sigma_staging_count)
    return False


def should_veto_after_admit(*_args: Any, **_kwargs: Any) -> bool:
    """Removed in — post-admit veto deleted; always False."""
    return False
