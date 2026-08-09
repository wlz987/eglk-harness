"""Mechanical Gate Γ — compare Claim vs Evidence (no LLM, no eval oracle)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from eglk_harness.domain import projections as P


@dataclass(frozen=True)
class GateDecision:
    decision: str  # admit | repair | abort
    reason: str
    maker_progress: float
    checker_progress: float
    perception_gap: float
    gaps_count: int
    should_run_next: bool
    next_action: str | None = None
    subgoal_id: str | None = None
    tick: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _as_list(x: Any) -> list[Any]:
    return list(x) if isinstance(x, (list, tuple)) else []


def _valid_artifacts(artifacts: list[Any]) -> list[str]:
    out: list[str] = []
    for a in artifacts:
        if isinstance(a, str) and a.strip():
            out.append(a.strip())
        elif isinstance(a, Mapping):
            for k in ("path", "text", "content", "uri"):
                v = a.get(k)
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
                    break
    return out


def _payload_empty(payload: Any) -> bool:
    if payload is None:
        return True
    if isinstance(payload, Mapping):
        if not payload:
            return True
        if "commands" in payload:
            return not payload.get("commands")
        if "files" in payload:
            return not payload.get("files")
        return False
    return not bool(payload)


def _alternatives_missing(claim: Mapping[str, Any], evidence: Mapping[str, Any]) -> bool:
    if claim.get("alternatives_missing") is True:
        return True
    if evidence.get("alternatives_missing") is True:
        return True
    alts = claim.get("alternatives")
    return not isinstance(alts, list) or len(alts) < 1


def decide(
    claim: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    quota: Mapping[str, Any] | None = None,
    repair_counts: Mapping[str, int] | None = None,
) -> GateDecision:
    """Pure Gate decision per design/kernel/gate_policy.md.

    ``repair_counts`` maps prior same-cause repair reasons → count *before* this tick.
    If a repair reason would fire and count already >= REPAIRS_MAX, return abort(*_exhausted).

    ``τ_focus`` / ``τ_unc`` are intentionally unused here (never abort).
    """
    quota = quota or {}
    counts = dict(repair_counts or {})

    done = _f(claim.get("done_progress"))
    audit = _f(evidence.get("audit_progress"))
    gap = abs(done - audit)

    gaps = [str(g) for g in _as_list(evidence.get("gaps"))]
    challenges = [str(c) for c in _as_list(evidence.get("challenges"))]
    merged_gaps = list(dict.fromkeys([*gaps, *challenges]))
    gaps_count = len(merged_gaps)

    subgoal_id = claim.get("subgoal_id") or evidence.get("subgoal_id")
    tick = claim.get("tick") if claim.get("tick") is not None else evidence.get("tick")
    tick_i = int(tick) if tick is not None else None
    sub_s = str(subgoal_id) if subgoal_id is not None else None

    def _out(
        decision: str,
        reason: str,
        *,
        should_run_next: bool | None = None,
        next_action: str | None = None,
    ) -> GateDecision:
        if should_run_next is None:
            should_run_next = decision == "repair"
        return GateDecision(
            decision=decision,
            reason=reason,
            maker_progress=done,
            checker_progress=audit,
            perception_gap=gap,
            gaps_count=gaps_count,
            should_run_next=should_run_next,
            next_action=next_action,
            subgoal_id=sub_s,
            tick=tick_i,
        )

    def _repair(reason: str) -> GateDecision:
        used = int(counts.get(reason, 0))
        if used >= P.REPAIRS_MAX:
            return _out(
                "abort",
                f"{reason}_exhausted",
                should_run_next=False,
                next_action="archive",
            )
        return _out("repair", reason, should_run_next=True, next_action="retry_leaf")

    tokens = int(quota.get("cognitive_tokens", 0) or 0)
    tokens_max = int(
        quota.get("cognitive_tokens_max", P.COGNITIVE_TOKENS_MAX) or P.COGNITIVE_TOKENS_MAX
    )
    if tokens >= tokens_max:
        return _out("abort", "cognitive_budget", should_run_next=False, next_action="archive")

    if _alternatives_missing(claim, evidence):
        return _repair("missing_alternatives")

    if evidence.get("integrity_violation") is True:
        return _repair("integrity_violation")

    artifacts = _valid_artifacts(_as_list(evidence.get("artifacts")))
    kind = claim.get("kind")
    payload = claim.get("payload")
    if not artifacts or (kind == "commands" and _payload_empty(payload)):
        return _repair("no_evidence_grounding")

    criteria_defect = evidence.get("criteria_defect") is True
    if audit >= P.TAU_DONE and criteria_defect and gap < P.TAU_GAP:
        return _out(
            "admit",
            "criteria_defect_acknowledged",
            should_run_next=False,
            next_action="advance",
        )

    if audit >= P.TAU_DONE and gaps_count == 0 and gap < P.TAU_GAP:
        return _out(
            "admit",
            "consistent_completion",
            should_run_next=False,
            next_action="advance",
        )

    if gap >= P.TAU_GAP:
        return _repair("perception_gap")

    if audit < P.TAU_DONE:
        return _repair("incomplete")

    if claim.get("shortcut_hit") is True and audit < 1.0:
        return _repair("shortcut_without_completion")

    if tokens >= tokens_max:
        return _out("abort", "cognitive_budget", should_run_next=False, next_action="archive")

    return _repair("incomplete")
