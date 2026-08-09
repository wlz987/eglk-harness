"""Validate domain documents against packaged JSON Schemas."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from eglk_harness.domain.json_extract import extract_json

_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


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
    if isinstance(tick, bool):
        return
    if isinstance(tick, float) and tick.is_integer():
        doc["tick"] = int(tick)
        return
    if isinstance(tick, str):
        try:
            doc["tick"] = int(tick.strip())
        except ValueError:
            # Timestamps / free text — drop so callers can inject the leaf tick.
            doc.pop("tick", None)


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


def coerce_document(name: str, doc: dict[str, Any]) -> dict[str, Any]:
    """Best-effort normalize common live-model drift before schema validation."""
    out = dict(doc)
    _coerce_tick(out)
    if name == "claim":
        _coerce_claim_alternatives(out)
    elif name == "evidence":
        _coerce_evidence_lists(out)
    return out


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
