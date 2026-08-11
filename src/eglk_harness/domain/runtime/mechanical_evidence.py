"""Deterministic EvidenceBundle from disk boundary (truth-blind; no Oracle)."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.obligation_compile import VERIFICATION_TYPES
from eglk_harness.domain.runtime.boundary_verify import (
    parse_boundary_rules,
    verify_boundary,
)

_INTENT_MECH_GAP = (
    "mechanical_checker: intent obligation requires independent LLM/scout attestation"
)


def _verification_type_map(
    obligation_refs: Sequence[str],
    obligation_verification_types: Mapping[str, str] | None,
) -> dict[str, str]:
    """When ``obligation_verification_types`` is omitted, preserve legacy boundary-only mechanical checks."""
    out: dict[str, str] = {}
    if obligation_verification_types is None:
        for oid in obligation_refs:
            oid_s = str(oid).strip()
            if oid_s:
                out[oid_s] = "file_exists"
        return out
    raw = obligation_verification_types
    for oid in obligation_refs:
        oid_s = str(oid).strip()
        if not oid_s:
            continue
        vt = str(raw.get(oid_s) or "custom_attestation")
        out[oid_s] = vt if vt in VERIFICATION_TYPES else "custom_attestation"
    return out


def has_intent_obligations(
    obligation_refs: Sequence[str],
    obligation_verification_types: Mapping[str, str] | None = None,
) -> bool:
    """True when any bound obligation requires custom_attestation (intent-level)."""
    if obligation_verification_types is None:
        return False
    type_map = _verification_type_map(obligation_refs, obligation_verification_types)
    if not type_map:
        return False
    return any(vt == "custom_attestation" for vt in type_map.values())


def checker_mechanical_enabled() -> bool:
    """Prefer mechanical Evidence when possible (default on)."""
    raw = os.environ.get("EGLK_CHECKER_MECHANICAL", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _file_attestation(
    *,
    rel: str,
    path: Path,
    world_revision: int,
    observer: str,
    method: str = "file_exists",
) -> dict[str, Any]:
    digest = _sha256_file(path) if path.is_file() else "missing"
    return {
        "method": method,
        "world_revision": int(world_revision),
        "digest": digest,
        "observer": observer,
        "raw_ref": rel,
        "watch_set": [rel],
    }


def _rel_from_file_write_action(workdir: Path, action: Mapping[str, Any]) -> str | None:
    payload = action.get("payload") if isinstance(action.get("payload"), Mapping) else {}
    target = str(action.get("target") or "").strip().lstrip("/").replace("\\", "/")
    rel = str(payload.get("path") or target).strip().lstrip("/").replace("\\", "/")
    if rel.startswith("workdir/"):
        rel = rel[len("workdir/") :]
    if not rel or ".." in Path(rel).parts:
        return None
    return rel


def _json_payload_body(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extract structured JSON body from file_write payload (WA agent_response shape)."""
    skip = frozenset({"path", "content", "text", "source", "format", "entries", "pages", "browser", "creator"})
    if not payload:
        return None
    body = {k: v for k, v in payload.items() if k not in skip}
    if body:
        return body
    return None


def _file_write_matches_disk(workdir: Path, action: Mapping[str, Any]) -> bool:
    rel = _rel_from_file_write_action(workdir, action)
    if not rel:
        return False
    path = workdir / rel
    if not path.is_file():
        return False
    payload = action.get("payload") if isinstance(action.get("payload"), Mapping) else {}
    if path.suffix.lower() == ".json":
        try:
            disk = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        body = _json_payload_body(payload)
        if isinstance(body, dict) and isinstance(disk, dict):
            return disk == body
    return True


def _claim_is_path_ack_only(claim: Mapping[str, Any]) -> bool:
    actions = [a for a in (claim.get("actions") or []) if isinstance(a, Mapping)]
    if not actions:
        return False
    return all(str(a.get("kind") or "") == "path_ack" for a in actions)


def synthesize_mechanical_evidence(
    *,
    workdir: Path,
    claim: Mapping[str, Any],
    contract_ref: str,
    obligation_refs: Sequence[str],
    boundary: Sequence[str],
    world_revision: int | None,
    tick: int,
    written: Sequence[str] | None = None,
    obligation_verification_types: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    """Build Evidence from MUST_EXIST / FORBIDDEN only — never reads eval scores.

    Returns None when there is no mechanical surface (empty boundary and no refs).
    """
    workdir = Path(workdir).resolve()
    refs = [str(x).strip() for x in obligation_refs if str(x).strip()]
    type_map = _verification_type_map(refs, obligation_verification_types)
    rules = parse_boundary_rules(boundary)
    if not refs and not rules.must_exist and not rules.forbidden_prefixes:
        return None

    wr = int(world_revision or 0)
    observer = f"checker-mech-{uuid.uuid4().hex[:10]}"
    violations = verify_boundary(workdir, boundary)
    boundary_ok = not violations

    atts: list[dict[str, Any]] = []
    for rel, _note in rules.must_exist:
        path = workdir / rel
        if path.is_file():
            method = "file_content_match" if rel.endswith(".json") else "file_exists"
            atts.append(
                _file_attestation(
                    rel=rel, path=path, world_revision=wr, observer=observer, method=method
                )
            )
    for rel in written or []:
        rel_s = str(rel).strip().lstrip("/")
        if not rel_s or any(a.get("raw_ref") == rel_s for a in atts):
            continue
        path = workdir / rel_s
        if path.is_file():
            atts.append(
                _file_attestation(rel=rel_s, path=path, world_revision=wr, observer=observer)
            )

    gaps = list(violations)
    claim_note = str(claim.get("note") or "")
    actions = [a for a in (claim.get("actions") or []) if isinstance(a, Mapping)]
    file_writes = [a for a in actions if str(a.get("kind") or "") == "file_write"]
    path_ack_only = _claim_is_path_ack_only(claim)

    content_bound = False
    if file_writes:
        matches = [_file_write_matches_disk(workdir, fw) for fw in file_writes]
        content_bound = all(matches)
        if not content_bound:
            gaps.append("mechanical_checker: file_write payload does not match on-disk content")
    elif path_ack_only and "mechanical_claim" in claim_note:
        gaps.append(
            "mechanical_checker: claim is path_ack only — content binding to leaf intent not verified"
        )
    elif not file_writes and "mechanical_claim" in claim_note:
        gaps.append(
            "mechanical_checker: claim is path_ack only — content binding to leaf intent not verified"
        )

    if not refs:
        refs = ["ob-unknown"]

    verdicts: list[dict[str, Any]] = []
    for oid in refs:
        vt = type_map.get(oid, "custom_attestation")
        if vt == "custom_attestation":
            verdicts.append(
                {
                    "obligation_id": oid,
                    "status": "unsatisfied",
                    "attestations": [],
                    "gaps": [_INTENT_MECH_GAP],
                    "defect_suspected": False,
                }
            )
            continue
        satisfied = boundary_ok and atts and not gaps
        if satisfied and file_writes and not content_bound:
            satisfied = False
        status = "satisfied" if satisfied else "unsatisfied"
        v_gaps = list(gaps) if status != "satisfied" else []
        v_atts = list(atts) if status == "satisfied" else []
        if status == "satisfied" and not v_atts:
            status = "unsatisfied"
            v_gaps = v_gaps or ["no_attestation"]
        verdicts.append(
            {
                "obligation_id": oid,
                "status": status,
                "attestations": v_atts,
                "gaps": v_gaps,
                "defect_suspected": False,
            }
        )

    additional = [g for g in gaps if g.startswith("boundary:")]

    return {
        "schema": P.EVIDENCE_BUNDLE_SCHEMA,
        "evidence_id": f"eb-mech-{tick:03d}-{uuid.uuid4().hex[:8]}",
        "contract_ref": contract_ref or "wc-unknown",
        "checker_session_id": observer,
        "world_revision": wr,
        "verdicts": verdicts,
        "integrity_violation": False,
        "additional_gaps": additional,
        "note": "mechanical_evidence_from_boundary",
    }
