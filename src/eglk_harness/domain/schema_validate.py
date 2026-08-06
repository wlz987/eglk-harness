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


def parse_and_validate(name: str, text: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        raw = extract_json(text)
    except ValueError as exc:
        return None, [str(exc)]
    if not isinstance(raw, dict):
        return None, ["extracted JSON is not an object"]
    errs = validate_document(name, raw)
    return (raw if not errs else None), errs
