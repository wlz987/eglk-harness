"""Validate domain documents against packaged JSON Schemas."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema
from referencing import Registry, Resource

from eglk_harness.domain.runtime.json_extract import extract_json

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"

# Legacy name map (callers may still say claim/evidence during transition)
_NAME_ALIASES = {
    "claim": "action_claim",
    "evidence": "evidence_bundle",
    "goal": "goal_spec",
    "leaf_contract": "work_contract",
    "state": "run_projection",
    "subgoals_tree": "task_structure",
    "sigma": "memory_record",
}


@lru_cache(maxsize=1)
def _registry() -> Registry:
    resources: list[tuple[str, Resource]] = []
    for path in _SCHEMA_DIR.glob("*.schema.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        resources.append((data["$id"], Resource.from_contents(data)))
        resources.append((path.name, Resource.from_contents(data)))
    return Registry().with_resources(resources)


@lru_cache(maxsize=32)
def _load_schema(name: str) -> dict[str, Any]:
    name = _NAME_ALIASES.get(name, name)
    path = _SCHEMA_DIR / f"{name}.schema.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"schema must be object: {path}")
    return data


def canonical_schema_name(name: str) -> str:
    return _NAME_ALIASES.get(name, name)


def validate_document(name: str, doc: Mapping[str, Any]) -> list[str]:
    """Return validation error strings (empty = ok)."""
    schema = _load_schema(name)
    validator = jsonschema.Draft202012Validator(schema, registry=_registry())
    return [e.message for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.path))]


def _as_list(x: Any) -> list[Any]:
    return list(x) if isinstance(x, (list, tuple)) else []


def _coerce_action_claim(doc: dict[str, Any]) -> None:
    doc["schema"] = "eglk.action_claim"
    if not isinstance(doc.get("claim_id"), str) or not doc.get("claim_id"):
        doc["claim_id"] = "claim-unknown"
    if not isinstance(doc.get("contract_ref"), str) or not doc.get("contract_ref"):
        doc["contract_ref"] = "wc-unknown"
    if not isinstance(doc.get("maker_session_id"), str) or not doc.get("maker_session_id"):
        doc["maker_session_id"] = "unknown"
    if not isinstance(doc.get("intent"), str) or not doc.get("intent"):
        doc["intent"] = "(unspecified)"
    if not isinstance(doc.get("actions"), list):
        doc["actions"] = []
    alts = doc.get("alternatives")
    if isinstance(alts, list) and alts:
        fixed = []
        for item in alts:
            if isinstance(item, str):
                fixed.append({"text": item, "status": "reject"})
            elif isinstance(item, dict):
                fixed.append(
                    {
                        "text": str(item.get("text") or item.get("id") or item.get("reason") or "(alt)"),
                        "status": item.get("status") if item.get("status") in {"adopt", "reject"} else "reject",
                        **({"reason": str(item["reason"])} if item.get("reason") is not None else {}),
                    }
                )
        doc["alternatives"] = fixed
    sa = doc.get("self_assessment")
    if not isinstance(sa, dict):
        # migrate 0.2.x top-level floats
        doc["self_assessment"] = {
            "done_progress": float(doc.pop("done_progress", 0.0) or 0.0),
            "confidence": float(doc.pop("confidence", 0.0) or 0.0),
        }
    else:
        doc["self_assessment"] = {
            "done_progress": max(0.0, min(1.0, float(sa.get("done_progress", 0.0) or 0.0))),
            "confidence": max(0.0, min(1.0, float(sa.get("confidence", 0.0) or 0.0))),
        }
    if not isinstance(doc.get("world_revision_base"), int):
        doc["world_revision_base"] = int(doc.get("world_revision_base") or 0)
    # Drop 0.2.x-only fields
    for k in ("tick", "kind", "payload", "step_review", "subgoal_id", "done_progress", "confidence"):
        doc.pop(k, None)


def _gap_text(item: Any) -> str:
    """Normalize gap entries that models emit as ``{gap: ...}`` objects."""
    if isinstance(item, Mapping):
        for key in ("gap", "text", "message", "reason"):
            val = item.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return json.dumps(item, ensure_ascii=False)
    return str(item).strip()


def _coerce_attestation(att: Mapping[str, Any], *, world_revision: int, observer: str) -> dict[str, Any]:
    out = dict(att)
    try:
        wr = int(out.get("world_revision", world_revision) or world_revision)
    except (TypeError, ValueError):
        wr = int(world_revision)
    out["world_revision"] = wr
    if not str(out.get("observer") or "").strip():
        out["observer"] = observer
    if not str(out.get("method") or "").strip():
        out["method"] = "custom_attestation"
    if not str(out.get("digest") or "").strip():
        out["digest"] = str(out.get("raw_ref") or "attestation")[:128] or "attestation"
    if not str(out.get("raw_ref") or "").strip():
        out["raw_ref"] = str(out.get("digest") or "attestation")
    ws = out.get("watch_set")
    if not isinstance(ws, list):
        out["watch_set"] = [str(ws)] if ws else []
    else:
        out["watch_set"] = [str(x) for x in ws if str(x).strip()]
    return out


def _coerce_verdict(verdict: Mapping[str, Any], *, world_revision: int, observer: str) -> dict[str, Any]:
    vd = dict(verdict)
    vd["obligation_id"] = str(vd.get("obligation_id") or "ob-unknown")
    status = str(vd.get("status") or "unsatisfied")
    if status not in {"satisfied", "unsatisfied", "indeterminate"}:
        status = "unsatisfied"
    vd["status"] = status
    vd["defect_suspected"] = bool(vd.get("defect_suspected"))
    gaps_raw = vd.get("gaps")
    if not isinstance(gaps_raw, list):
        gaps_raw = [gaps_raw] if gaps_raw else []
    vd["gaps"] = [g for g in (_gap_text(x) for x in gaps_raw) if g]
    atts_in = vd.get("attestations")
    if not isinstance(atts_in, list):
        atts_in = []
    vd["attestations"] = [
        _coerce_attestation(a, world_revision=world_revision, observer=observer)
        for a in atts_in
        if isinstance(a, Mapping)
    ]
    return vd


def _coerce_evidence_bundle(doc: dict[str, Any]) -> None:
    if not isinstance(doc.get("evidence_id"), str) or not doc.get("evidence_id"):
        doc["evidence_id"] = "evidence-unknown"
    if not isinstance(doc.get("contract_ref"), str) or not doc.get("contract_ref"):
        doc["contract_ref"] = "wc-unknown"
    if not isinstance(doc.get("checker_session_id"), str) or not doc.get("checker_session_id"):
        doc["checker_session_id"] = "unknown"
    if not isinstance(doc.get("world_revision"), int):
        try:
            doc["world_revision"] = int(doc.get("world_revision") or 0)
        except (TypeError, ValueError):
            doc["world_revision"] = 0
    if "integrity_violation" not in doc:
        doc["integrity_violation"] = False
    observer = str(doc["checker_session_id"])
    wr = int(doc["world_revision"])

    # Normalize additional_gaps whether already a list or lifted from legacy gaps.
    if not isinstance(doc.get("additional_gaps"), list):
        gaps = [_gap_text(g) for g in _as_list(doc.get("gaps"))]
        doc["additional_gaps"] = [g for g in gaps if g.startswith("boundary:")]
    else:
        doc["additional_gaps"] = [g for g in (_gap_text(x) for x in doc["additional_gaps"]) if g]

    if not isinstance(doc.get("verdicts"), list) or not doc["verdicts"]:
        # migrate 0.2.x flat evidence into a single indeterminate verdict
        artifacts = _as_list(doc.get("artifacts"))
        gaps = [
            g
            for g in (_gap_text(x) for x in _as_list(doc.get("gaps")))
            if g and not g.startswith("boundary:")
        ]
        atts = []
        for a in artifacts:
            if isinstance(a, str) and a.strip():
                atts.append(
                    {
                        "method": "custom_attestation",
                        "world_revision": wr,
                        "digest": a.strip()[:128],
                        "observer": observer,
                        "raw_ref": a.strip(),
                        "watch_set": [],
                    }
                )
            elif isinstance(a, dict):
                ref = str(a.get("path") or a.get("uri") or a.get("text") or "").strip()
                if ref:
                    atts.append(
                        {
                            "method": "custom_attestation",
                            "world_revision": wr,
                            "digest": ref[:128],
                            "observer": observer,
                            "raw_ref": ref,
                            "watch_set": [ref] if "/" in ref or ref.endswith((".txt", ".json", ".md")) else [],
                        }
                    )
        status = "satisfied" if atts and not gaps else "unsatisfied"
        if status == "satisfied" and not atts:
            status = "unsatisfied"
        doc["verdicts"] = [
            {
                "obligation_id": str(doc.get("obligation_id") or "ob-unknown"),
                "status": status if atts or status != "satisfied" else "unsatisfied",
                "attestations": atts if status == "satisfied" else atts,
                "gaps": gaps,
                "defect_suspected": bool(doc.get("criteria_defect") or False),
            }
        ]
        if doc["verdicts"][0]["status"] == "satisfied" and not doc["verdicts"][0]["attestations"]:
            doc["verdicts"][0]["status"] = "unsatisfied"
    else:
        doc["verdicts"] = [
            _coerce_verdict(v, world_revision=wr, observer=observer)
            for v in doc["verdicts"]
            if isinstance(v, Mapping)
        ]
    for k in (
        "tick",
        "gaps",
        "alternatives",
        "challenges",
        "artifacts",
        "audit_progress",
        "audit_confidence",
        "alternatives_missing",
        "cost_usd",
        "criteria_defect",
        "subgoal_id",
    ):
        doc.pop(k, None)


def _allowed_keys(name: str) -> set[str]:
    props = _load_schema(name).get("properties") or {}
    return set(props) if isinstance(props, dict) else set()


def _strip_unknown(doc: dict[str, Any], name: str) -> None:
    allowed = _allowed_keys(name)
    for key in list(doc.keys()):
        if key not in allowed:
            doc.pop(key, None)


def coerce_document(name: str, doc: dict[str, Any]) -> dict[str, Any]:
    """Best-effort normalize common live-model drift before schema validation."""
    out = dict(doc)
    cname = canonical_schema_name(name)
    if cname == "action_claim":
        _coerce_action_claim(out)
    elif cname == "evidence_bundle":
        _coerce_evidence_bundle(out)
    if "schema" not in out:
        out["schema"] = f"eglk.{cname}"
    _strip_unknown(out, cname)
    return out


def try_parse_document(name: str, text: str) -> tuple[dict[str, Any] | None, list[str]]:
    return parse_and_validate(name, text)


def parse_and_validate(name: str, text: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        raw = extract_json(text)
    except ValueError as exc:
        return None, [str(exc)]
    if not isinstance(raw, dict):
        return None, ["extracted JSON is not an object"]
    raw = coerce_document(name, raw)
    errs = validate_document(name, raw)
    return (raw if not errs else None), errs
