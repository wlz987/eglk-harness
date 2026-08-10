"""Deterministic ActionClaim synthesis when boundary is satisfied (no Oracle)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.runtime.boundary_verify import (
    parse_boundary_rules,
    promote_staged_deliverables,
    verify_boundary,
)


def list_satisfied_must_exist(workdir: Path, boundary: Sequence[str]) -> list[str]:
    """Return MUST_EXIST paths that pass mechanical validity on disk."""
    workdir = workdir.resolve()
    promote_staged_deliverables(workdir, boundary)
    violations = verify_boundary(workdir, boundary)
    if violations:
        return []
    rules = parse_boundary_rules(boundary)
    out: list[str] = []
    for rel, _note in rules.must_exist:
        if (workdir / rel).is_file():
            out.append(rel)
    return out


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def _intent_from_json_payload(data: Mapping[str, Any], title: str) -> str:
    if "retrieved_data" in data:
        return f"{title} (retrieved_data={data.get('retrieved_data')})"
    if data.get("status"):
        return f"{title} (status={data.get('status')})"
    return title


def _action_for_deliverable(
    workdir: Path,
    rel: str,
    *,
    tick: int,
    index: int,
) -> dict[str, Any]:
    """JSON deliverables → file_write with on-disk payload; others → path_ack."""
    path = workdir / rel
    action_id = f"ack-{tick:03d}-{index}"
    if rel.endswith(".json") and path.is_file():
        data = _read_json_object(path)
        if data is not None:
            return {
                "action_id": action_id,
                "kind": "file_write",
                "side_effect_class": "reversible",
                "target": rel,
                "payload": dict(data),
            }
    return {
        "action_id": action_id,
        "kind": "path_ack",
        "side_effect_class": "read_only",
        "target": f"workdir/{rel}",
        "payload": {"path": rel, "source": "mechanical_boundary"},
    }


def synthesize_mechanical_claim(
    *,
    workdir: Path,
    title: str,
    subgoal_id: str,
    contract_ref: str,
    world_revision: int | None,
    obligation_refs: Sequence[str],
    boundary: Sequence[str],
    tick: int,
    maker_session_id: str | None = None,
) -> dict[str, Any] | None:
    """Build Claim from on-disk MUST_EXIST — JSON as file_write, else path_ack.

    Gate truth-blind: binds file content for structured deliverables so mechanical
    Checker can attest ``file_content_match`` (not path_ack-only dead-end).
    """
    paths = list_satisfied_must_exist(workdir, boundary)
    if not paths:
        return None
    sid = (maker_session_id or "").strip() or f"maker-mech-{uuid.uuid4().hex[:12]}"
    actions: list[dict[str, Any]] = []
    intent = title
    for i, rel in enumerate(paths):
        act = _action_for_deliverable(workdir, rel, tick=tick, index=i)
        actions.append(act)
        if act.get("kind") == "file_write":
            pl = act.get("payload") or {}
            if isinstance(pl, Mapping):
                intent = _intent_from_json_payload(pl, title)

    has_file_write = any(a.get("kind") == "file_write" for a in actions)
    note = "mechanical_claim_from_disk" if has_file_write else "mechanical_claim_from_boundary"
    return {
        "schema": P.ACTION_CLAIM_SCHEMA,
        "claim_id": f"claim-mech-{tick:03d}-{uuid.uuid4().hex[:8]}",
        "contract_ref": contract_ref,
        "maker_session_id": sid,
        "intent": intent,
        "actions": actions,
        "alternatives": [
            {
                "text": "omit ActionClaim and rely on disk only",
                "status": "reject",
                "reason": "WorkContract requires typed ActionClaim for Gate",
            }
        ],
        "self_assessment": {"done_progress": 1.0, "confidence": 0.85},
        "world_revision_base": int(world_revision or 0),
        "node_id": subgoal_id,
        "tick": tick,
        "subgoal_id": subgoal_id,
        "note": note,
    }


def _normalize_rel(target: str) -> str:
    t = str(target or "").strip().lstrip("/").replace("\\", "/")
    if t.startswith("workdir/"):
        return t[len("workdir/") :]
    return t


def claim_file_writes_match_disk(
    claim: Mapping[str, Any],
    workdir: Path,
    boundary: Sequence[str],
) -> bool:
    """True when every JSON MUST_EXIST has a matching file_write payload."""
    from eglk_harness.domain.runtime.mechanical_evidence import _file_write_matches_disk

    workdir = workdir.resolve()
    paths = list_satisfied_must_exist(workdir, boundary)
    json_paths = [p for p in paths if p.endswith(".json")]
    if not json_paths:
        return True
    actions = [a for a in (claim.get("actions") or []) if isinstance(a, Mapping)]
    file_writes = [a for a in actions if str(a.get("kind") or "") == "file_write"]
    if not file_writes:
        return False
    for rel in json_paths:
        matched = any(
            _normalize_rel(str(fw.get("target") or "")) == rel and _file_write_matches_disk(workdir, fw)
            for fw in file_writes
        )
        if not matched:
            return False
    return True


def rebind_claim_from_disk(
    claim: Mapping[str, Any],
    workdir: Path,
    boundary: Sequence[str],
) -> dict[str, Any]:
    """Replace file_write payloads with on-disk JSON for satisfied MUST_EXIST paths."""
    workdir = workdir.resolve()
    paths = list_satisfied_must_exist(workdir, boundary)
    json_paths = [p for p in paths if p.endswith(".json")]
    if not json_paths:
        return dict(claim)
    disk_by_rel: dict[str, dict[str, Any]] = {}
    for rel in json_paths:
        data = _read_json_object(workdir / rel)
        if data is not None:
            disk_by_rel[rel] = data
    if not disk_by_rel:
        return dict(claim)

    out = dict(claim)
    actions: list[dict[str, Any]] = []
    covered: set[str] = set()
    for raw in out.get("actions") or []:
        if not isinstance(raw, Mapping):
            continue
        act = dict(raw)
        kind = str(act.get("kind") or "")
        if kind == "file_write":
            rel = _normalize_rel(str(act.get("target") or ""))
            data = disk_by_rel.get(rel)
            if data is not None:
                act["target"] = rel
                act["payload"] = dict(data)
                covered.add(rel)
        actions.append(act)

    tick = int(out.get("tick") or 0)
    for i, (rel, data) in enumerate(sorted(disk_by_rel.items())):
        if rel in covered:
            continue
        actions.append(
            {
                "action_id": f"disk-{tick:03d}-{i}",
                "kind": "file_write",
                "side_effect_class": "reversible",
                "target": rel,
                "payload": dict(data),
            }
        )

    out["actions"] = actions
    return out


def prefer_disk_bound_claim(
    claim: Mapping[str, Any] | None,
    *,
    workdir: Path,
    boundary: Sequence[str],
    title: str,
    subgoal_id: str,
    contract_ref: str,
    world_revision: int | None,
    obligation_refs: Sequence[str],
    tick: int,
    maker_session_id: str | None = None,
) -> dict[str, Any] | None:
    """Return disk-bound claim: rebind LLM claim or synthesize mechanical when boundary is met."""
    mech = synthesize_mechanical_claim(
        workdir=workdir,
        title=title,
        subgoal_id=subgoal_id,
        contract_ref=contract_ref,
        world_revision=world_revision,
        obligation_refs=obligation_refs,
        boundary=boundary,
        tick=tick,
        maker_session_id=maker_session_id,
    )
    if mech is None:
        if claim is not None:
            return rebind_claim_from_disk(claim, workdir, boundary)
        return None
    if claim is None:
        return mech
    rebound = rebind_claim_from_disk(claim, workdir, boundary)
    if claim_file_writes_match_disk(rebound, workdir, boundary):
        rebound["note"] = str(rebound.get("note") or "claim_rebound_from_disk")
        return rebound
    sid = str(claim.get("maker_session_id") or mech.get("maker_session_id") or "")
    mech["maker_session_id"] = sid or mech.get("maker_session_id")
    return mech
