"""Validate domain documents against packaged JSON Schemas."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from eglk_harness.domain.runtime.json_extract import extract_json

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


@lru_cache(maxsize=32)
def _load_schema(name: str) -> dict[str, Any]:
    path = _SCHEMA_DIR / f"{name}.schema.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"schema must be object: {path}")
    return data


def validate_document(name: str, doc: Mapping[str, Any]) -> list[str]:
    """Return validation error strings (empty = ok)."""
    schema = _load_schema(name)
    validator = jsonschema.Draft202012Validator(schema)
    return [e.message for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.path))]


def _coerce_tick(doc: dict[str, Any]) -> None:
    tick = doc.get("tick")
    if tick is None:
        doc["tick"] = 0
        return
    if isinstance(tick, bool):
        doc["tick"] = 0
        return
    if isinstance(tick, int):
        if tick < 0:
            doc["tick"] = 0
        return
    if isinstance(tick, float) and tick.is_integer():
        doc["tick"] = int(tick)
        return
    if isinstance(tick, str):
        try:
            doc["tick"] = int(tick.strip())
        except ValueError:
            # Timestamps / free text — placeholder; actors overwrite with leaf tick.
            doc["tick"] = 0
        return
    doc["tick"] = 0


def _coerce_claim_alternatives(doc: dict[str, Any]) -> None:
    alts = doc.get("alternatives")
    if not isinstance(alts, list):
        return
    fixed: list[Any] = []
    for item in alts:
        if isinstance(item, str):
            fixed.append(item)
            continue
        if not isinstance(item, dict):
            fixed.append(item)
            continue
        if "text" in item and "status" in item:
            obj = {
                "text": str(item["text"]),
                "status": str(item["status"]),
            }
            if item.get("reason") is not None:
                obj["reason"] = str(item["reason"])
            fixed.append(obj)
            continue
        # Common LLM drift: {id, reason} / {name, reason}
        text = item.get("text") or item.get("id") or item.get("name") or item.get("alt")
        reason = item.get("reason") or item.get("why")
        status = item.get("status") or "reject"
        if text is None and reason is not None:
            text = str(reason)
        if text is None:
            fixed.append(item)
            continue
        obj = {
            "text": str(text),
            "status": str(status) if status in {"adopt", "reject"} else "reject",
        }
        if reason is not None:
            obj["reason"] = str(reason)
        fixed.append(obj)
    doc["alternatives"] = fixed


def _coerce_evidence_lists(doc: dict[str, Any]) -> None:
    for key in ("gaps", "alternatives", "challenges", "artifacts"):
        val = doc.get(key)
        if not isinstance(val, list):
            continue
        doc[key] = [
            json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x)
            for x in val
        ]


def _as_str_list(val: Any) -> list[str] | None:
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    if isinstance(val, list):
        out = [
            json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x).strip()
            for x in val
            if x is not None and str(x).strip()
        ]
        return out or None
    return None


def _coerce_claim_step_review(doc: dict[str, Any]) -> None:
    raw = doc.get("step_review")
    if raw is None:
        # common Chinese / alternate top-level keys
        for alt in ("本步自评", "review", "stepReview"):
            if isinstance(doc.get(alt), dict):
                raw = doc.pop(alt)
                break
    if not isinstance(raw, dict):
        return
    mapping = {
        "gains": ("gains", "得", "gain", "所得"),
        "losses": ("losses", "失", "loss", "sacrifices", "放弃"),
        "benefits": ("benefits", "收益", "benefit", "回报"),
        "risks": ("risks", "风险", "risk", "残留风险"),
    }
    fixed: dict[str, Any] = {}
    for canon, aliases in mapping.items():
        val = None
        for key in aliases:
            if key in raw:
                val = raw[key]
                break
        coerced = _as_str_list(val)
        if coerced is not None:
            fixed[canon] = coerced
    doc["step_review"] = fixed


def _allowed_keys(name: str) -> set[str]:
    props = _load_schema(name).get("properties") or {}
    return set(props) if isinstance(props, dict) else set()


def _strip_unknown(doc: dict[str, Any], name: str) -> None:
    """Drop keys not in schema properties (keep additionalProperties: false strict)."""
    allowed = _allowed_keys(name)
    for key in list(doc.keys()):
        if key not in allowed:
            doc.pop(key, None)


def _coerce_claim_defaults(doc: dict[str, Any]) -> None:
    tick = doc.get("tick", 0)
    if not isinstance(tick, int):
        tick = 0
    if not isinstance(doc.get("claim_id"), str) or not str(doc.get("claim_id")).strip():
        doc["claim_id"] = f"claim-{tick}"
    if not isinstance(doc.get("maker_session_id"), str) or not str(doc.get("maker_session_id")).strip():
        doc["maker_session_id"] = "unknown"
    kind = doc.get("kind")
    if kind not in {"patch", "actions", "commands", "mixed", "files"}:
        doc["kind"] = "mixed"
    if not isinstance(doc.get("done_progress"), (int, float)) or isinstance(doc.get("done_progress"), bool):
        doc["done_progress"] = 0.0
    else:
        doc["done_progress"] = max(0.0, min(1.0, float(doc["done_progress"])))
    if not isinstance(doc.get("confidence"), (int, float)) or isinstance(doc.get("confidence"), bool):
        doc["confidence"] = 0.0
    else:
        doc["confidence"] = max(0.0, min(1.0, float(doc["confidence"])))
    alts = doc.get("alternatives")
    if not isinstance(alts, list) or not alts:
        doc["alternatives"] = ["(none)"]
    if not isinstance(doc.get("payload"), dict):
        doc["payload"] = {}
    sr = doc.get("step_review")
    if not isinstance(sr, dict):
        doc["step_review"] = {
            "gains": ["(coerced) unspecified gains"],
            "losses": ["(coerced) unspecified losses"],
            "benefits": ["(coerced) unspecified benefits"],
            "risks": ["(coerced) unspecified risks"],
        }


def _coerce_evidence_defaults(doc: dict[str, Any]) -> None:
    tick = doc.get("tick", 0)
    if not isinstance(tick, int):
        tick = 0
        doc["tick"] = 0
    if not isinstance(doc.get("evidence_id"), str) or not str(doc.get("evidence_id")).strip():
        doc["evidence_id"] = f"evidence-{tick}"
    if not isinstance(doc.get("checker_session_id"), str) or not str(doc.get("checker_session_id")).strip():
        doc["checker_session_id"] = "unknown"
    if not isinstance(doc.get("audit_progress"), (int, float)) or isinstance(doc.get("audit_progress"), bool):
        doc["audit_progress"] = 0.0
    else:
        doc["audit_progress"] = max(0.0, min(1.0, float(doc["audit_progress"])))
    if not isinstance(doc.get("audit_confidence"), (int, float)) or isinstance(
        doc.get("audit_confidence"), bool
    ):
        doc["audit_confidence"] = 0.0
    else:
        doc["audit_confidence"] = max(0.0, min(1.0, float(doc["audit_confidence"])))
    for key in ("gaps", "alternatives", "challenges", "artifacts"):
        if not isinstance(doc.get(key), list):
            doc[key] = []
    if "alternatives_missing" not in doc or not isinstance(doc.get("alternatives_missing"), bool):
        doc["alternatives_missing"] = False
    if not isinstance(doc.get("cost_usd"), (int, float)) or isinstance(doc.get("cost_usd"), bool):
        doc["cost_usd"] = 0.0
    else:
        doc["cost_usd"] = max(0.0, float(doc["cost_usd"]))


def _ensure_step_review_complete(doc: dict[str, Any]) -> None:
    sr = doc.get("step_review")
    if not isinstance(sr, dict):
        return
    for key, placeholder in (
        ("gains", "(coerced) unspecified gains"),
        ("losses", "(coerced) unspecified losses"),
        ("benefits", "(coerced) unspecified benefits"),
        ("risks", "(coerced) unspecified risks"),
    ):
        val = sr.get(key)
        if not isinstance(val, list) or not val or not all(isinstance(x, str) and x.strip() for x in val):
            sr[key] = [placeholder]


def coerce_document(name: str, doc: dict[str, Any]) -> dict[str, Any]:
    """Best-effort normalize common live-model drift before schema validation."""
    out = dict(doc)
    _coerce_tick(out)
    if name == "claim":
        _coerce_claim_alternatives(out)
        _coerce_claim_step_review(out)
        _coerce_claim_defaults(out)
        _ensure_step_review_complete(out)
    elif name == "evidence":
        _coerce_evidence_lists(out)
        _coerce_evidence_defaults(out)
    _strip_unknown(out, name)
    return out


def try_parse_document(name: str, text: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract + coerce + validate; used by format_repair before LLM retries."""
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
