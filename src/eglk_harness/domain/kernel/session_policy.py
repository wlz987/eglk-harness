"""Fresh-session policy — mechanical enforcement of GOAL §1.10."""

from __future__ import annotations

import uuid
from typing import Any, Mapping, Sequence

from eglk_harness.domain.event_store import EventEnvelope


def _session_contract_map(events: Sequence[EventEnvelope]) -> dict[str, str]:
    """Map session_id → contract_ref for Maker/Checker sessions."""
    out: dict[str, str] = {}
    for ev in events:
        p = ev.payload or {}
        if ev.type == "ActionDispatched":
            sid = str(p.get("maker_session_id") or "")
            cref = str(p.get("contract_ref") or "")
            if sid and cref:
                out[sid] = cref
        elif ev.type == "EvidenceRecorded":
            evdoc = p.get("evidence") if isinstance(p.get("evidence"), Mapping) else p
            sid = str(evdoc.get("checker_session_id") or "")
            cref = str(evdoc.get("contract_ref") or "")
            if sid and cref:
                out[sid] = cref
    return out


def validate_maker_session(
    claim: Mapping[str, Any],
    events: Sequence[EventEnvelope],
) -> tuple[bool, str]:
    contract_ref = str(claim.get("contract_ref") or "")
    sid = str(claim.get("maker_session_id") or "").strip()
    if not contract_ref:
        return False, "missing_contract_ref"
    if not sid:
        return False, "missing_maker_session_id"
    mapping = _session_contract_map(events)
    prior = mapping.get(sid)
    if prior is not None and prior != contract_ref:
        return False, "session_reused_across_contracts"
    return True, "ok"


def validate_checker_session(
    evidence: Mapping[str, Any],
    *,
    maker_session_id: str | None,
    events: Sequence[EventEnvelope],
) -> tuple[bool, str]:
    contract_ref = str(evidence.get("contract_ref") or "")
    sid = str(evidence.get("checker_session_id") or "").strip()
    if not contract_ref:
        return False, "missing_contract_ref"
    if not sid:
        return False, "missing_checker_session_id"
    if maker_session_id and sid == str(maker_session_id):
        return False, "maker_equals_checker"
    mapping = _session_contract_map(events)
    prior = mapping.get(sid)
    if prior is not None and prior != contract_ref:
        return False, "session_reused_across_contracts"
    return True, "ok"


def assign_maker_session(claim: dict[str, Any], contract_ref: str) -> str:
    sid = str(claim.get("maker_session_id") or "").strip()
    if not sid or sid == "unknown":
        sid = f"maker-{uuid.uuid4().hex[:12]}"
    claim["maker_session_id"] = sid
    claim["contract_ref"] = contract_ref
    return sid


def assign_checker_session(
    evidence: dict[str, Any],
    contract_ref: str,
    *,
    maker_session_id: str,
) -> str:
    sid = str(evidence.get("checker_session_id") or "").strip()
    if not sid or sid == "unknown" or sid == maker_session_id:
        sid = f"checker-{uuid.uuid4().hex[:12]}"
    evidence["checker_session_id"] = sid
    evidence["contract_ref"] = contract_ref
    return sid
