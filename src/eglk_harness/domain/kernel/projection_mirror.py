"""Read-only audit mirrors derived from events — not authority (GOAL §1.7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from eglk_harness.domain.event_store import EventEnvelope


def _write_json(path: Path, data: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def latest_gate_decision(events: Sequence[EventEnvelope]) -> dict[str, Any] | None:
    for ev in reversed(events):
        if ev.type == "GateDecided":
            p = ev.payload or {}
            return dict(p) if isinstance(p, Mapping) else None
    return None


def latest_claim_evidence(events: Sequence[EventEnvelope]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    claim: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    for ev in reversed(events):
        p = ev.payload or {}
        if evidence is None and ev.type == "EvidenceRecorded":
            raw = p.get("evidence") if isinstance(p.get("evidence"), Mapping) else p
            evidence = dict(raw)
        if claim is None and ev.type == "ActionDispatched":
            raw = p.get("claim") if isinstance(p.get("claim"), Mapping) else p
            claim = dict(raw)
        if claim is not None and evidence is not None:
            break
    return claim, evidence


def mirror_audit_artifacts(
    loop_dir: Path,
    events: Sequence[EventEnvelope],
    *,
    tick: int | None = None,
) -> dict[str, str]:
    """Write claims/evidence/decisions mirrors from EventStore tail (dashboard only)."""
    claim, evidence = latest_claim_evidence(events)
    decision = latest_gate_decision(events)
    suffix = f"{tick:03d}" if tick is not None else "latest"
    out: dict[str, str] = {}
    meta = {
        "authority": "events.db",
        "kind": "audit_mirror",
        "note": "derived from EventStore; not Gate input",
    }
    if claim is not None:
        p = loop_dir / "claims" / f"{suffix}.json"
        _write_json(p, {**claim, "_mirror": meta})
        out["claim"] = str(p)
    if evidence is not None:
        p = loop_dir / "evidence" / f"{suffix}.json"
        _write_json(p, {**evidence, "_mirror": meta})
        out["evidence"] = str(p)
    if decision is not None:
        p = loop_dir / "decisions" / f"{suffix}.json"
        _write_json(p, {**decision, "_mirror": meta})
        out["decision"] = str(p)
    return out
