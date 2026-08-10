"""Mechanical Gate Γ — per-obligation reduction.

Pure function: WorkContract + ActionClaim + EvidenceBundle → GateDecision.
Never reads self_assessment floats, eval scorers, or candidates/.
Abort only for cognitive_budget / *_exhausted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.attestation import (
    obligation_type_map,
    verdict_has_valid_attestation,
)
from eglk_harness.domain.kernel.repair_counts import closure_repair_key, repair_count_key
from eglk_harness.domain.kernel.projections import GATE_DECISION_SCHEMA

_ABORT_REASONS = frozenset(
    {
        "cognitive_budget",
        "integrity_violation_exhausted",
        "no_attestation_exhausted",
        "boundary_unmet_exhausted",
        "amendment_pending_exhausted",
        "closure_incomplete_exhausted",
        "capability_ceiling_exceeded_exhausted",
        "capability_denied_exhausted",
        "missing_alternatives_exhausted",
    }
)

ABORT_REASONS = _ABORT_REASONS


@dataclass(frozen=True)
class GateDecision:
    decision: str  # admit | repair | abort
    reason: str
    node_id: str
    contract_ref: str
    satisfied_obligation_ids: list[str]
    open_obligation_ids: list[str]
    is_closure_gate: bool = False
    event_ref: str | None = None
    schema: str = GATE_DECISION_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "decision": self.decision,
            "reason": self.reason,
            "node_id": self.node_id,
            "contract_ref": self.contract_ref,
            "satisfied_obligation_ids": list(self.satisfied_obligation_ids),
            "open_obligation_ids": list(self.open_obligation_ids),
            "is_closure_gate": self.is_closure_gate,
            "event_ref": self.event_ref,
        }


def _as_list(x: Any) -> list[Any]:
    return list(x) if isinstance(x, (list, tuple)) else []


def _alternatives_missing(claim: Mapping[str, Any]) -> bool:
    alts = claim.get("alternatives")
    return not isinstance(alts, list) or len(alts) < 1


def _ceiling_exceeded(contract: Mapping[str, Any], claim: Mapping[str, Any]) -> bool:
    policy = contract.get("transaction_policy") or {}
    ceiling = set(_as_list(policy.get("side_effect_class_ceiling")))
    if not ceiling:
        return False
    for action in _as_list(claim.get("actions")):
        if not isinstance(action, Mapping):
            continue
        sec = action.get("side_effect_class")
        if sec not in ceiling:
            return True
    return False


def _verdict_map(evidence: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for v in _as_list(evidence.get("verdicts")):
        if isinstance(v, Mapping) and v.get("obligation_id"):
            out[str(v["obligation_id"])] = v
    return out


def decide(
    contract: Mapping[str, Any],
    claim: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    quota: Mapping[str, Any] | None = None,
    repair_counts: Mapping[str, int] | None = None,
    pending_amendment_obligation_ids: Sequence[str] | None = None,
    is_closure_gate: bool = False,
    closure_complete: bool | None = None,
) -> GateDecision:
    """Per-obligation mechanical reduction.

    ``repair_counts`` maps prior same-cause repair reasons → count *before* this decision.
    Gate MUST NOT read ``claim.self_assessment``.
    """
    quota = quota or {}
    counts = dict(repair_counts or {})
    node_id = str(contract.get("node_id") or claim.get("node_id") or "")
    contract_ref = str(contract.get("contract_id") or claim.get("contract_ref") or "")
    obligation_refs = [str(x) for x in _as_list(contract.get("obligation_refs"))]
    pending_amend = set(str(x) for x in (pending_amendment_obligation_ids or []))

    satisfied: list[str] = []
    open_ids: list[str] = []

    def _out(decision: str, reason: str, *, sat: list[str] | None = None, open_: list[str] | None = None) -> GateDecision:
        return GateDecision(
            decision=decision,
            reason=reason,
            node_id=node_id,
            contract_ref=contract_ref,
            satisfied_obligation_ids=list(sat if sat is not None else satisfied),
            open_obligation_ids=list(open_ if open_ is not None else open_ids),
            is_closure_gate=is_closure_gate,
        )

    def _repair_count_used(reason: str, obligation_id: str) -> int:
        key = repair_count_key(obligation_id, reason)
        if reason == "closure_incomplete":
            key = closure_repair_key()
        legacy = int(counts.get(reason, 0))
        return max(int(counts.get(key, 0)), legacy)

    def _repair(reason: str, obligation_id: str | None = None) -> GateDecision:
        oid = obligation_id or (pending[0] if pending else "__all__")
        if reason == "closure_incomplete":
            oid = "__closure__"
        used = _repair_count_used(reason, oid)
        repairs_cap = int(quota.get("repairs_max", P.REPAIRS_MAX) or P.REPAIRS_MAX)
        if used >= repairs_cap:
            abort_reason = f"{reason}_exhausted"
            if abort_reason not in _ABORT_REASONS:
                abort_reason = f"{reason}_exhausted"
            return _out("abort", abort_reason)
        if oid not in open_ids and oid not in ("__all__", "__closure__"):
            open_ids.append(oid)
        return _out("repair", reason)

    tokens = int(quota.get("cognitive_tokens", 0) or 0)
    tokens_max = int(
        quota.get("cognitive_tokens_max", P.COGNITIVE_TOKENS_MAX) or P.COGNITIVE_TOKENS_MAX
    )

    if _ceiling_exceeded(contract, claim):
        return _repair("capability_ceiling_exceeded", "__all__")

    if _alternatives_missing(claim):
        return _repair("missing_alternatives", "__all__")

    if evidence.get("integrity_violation") is True:
        open_ids = list(obligation_refs)
        return _repair("integrity_violation", obligation_refs[0] if obligation_refs else "__all__")

    verdicts = _verdict_map(evidence)
    type_map = obligation_type_map(contract)
    try:
        expected_rev = int(evidence["world_revision"]) if "world_revision" in evidence else None
    except (TypeError, ValueError):
        expected_rev = None
    pending: list[str] = []
    for oid in obligation_refs:
        v = verdicts.get(oid)
        if v is None:
            pending.append(oid)
            open_ids.append(oid)
            continue
        status = v.get("status")
        if status == "satisfied":
            if not verdict_has_valid_attestation(
                v,
                verification_type=type_map.get(oid),
                expected_world_revision=expected_rev,
            ):
                return _repair("no_attestation", oid)
            satisfied.append(oid)
        else:
            pending.append(oid)
            open_ids.append(oid)

    additional_gaps = [str(g) for g in _as_list(evidence.get("additional_gaps"))]
    if any(g.startswith("boundary:") for g in additional_gaps):
        return _repair("boundary_unmet", pending[0] if pending else (obligation_refs[0] if obligation_refs else "__all__"))

    if pending_amend.intersection(obligation_refs):
        return _repair("amendment_pending", next(iter(pending_amend.intersection(obligation_refs))))

    if is_closure_gate:
        if closure_complete is False:
            return _repair("closure_incomplete", "__closure__")
        if pending:
            if tokens >= tokens_max:
                return _out("abort", "cognitive_budget")
            return _repair("closure_incomplete", "__closure__")
        return _out("admit", "closure_admitted", sat=satisfied, open_=[])

    if not pending:
        return _out("admit", "obligations_satisfied", sat=satisfied, open_=[])

    # Design gate_policy: cognitive abort only when obligations still pending.
    if tokens >= tokens_max:
        return _out("abort", "cognitive_budget")

    first = pending[0]
    v = verdicts.get(first)
    if v is None:
        return _repair("no_attestation", first)
    for g in _as_list(v.get("gaps")):
        if str(g).startswith("boundary:"):
            return _repair("boundary_unmet", first)
    return _repair("no_attestation", first)
