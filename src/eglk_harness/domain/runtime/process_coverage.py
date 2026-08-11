"""Process coverage sidecar — schema validation (truth-blind; no Oracle)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

PROCESS_COVERAGE_SCHEMA = "eglk.process_coverage"
_COVERAGE_ALIASES = frozenset(
    {
        "process_coverage.json",
        "coverage_note.json",
    }
)
_ENUMERATION_CUE_RE = re.compile(
    r"\b(all|every|each|names?\s+of|list\s+of|how\s+many|total\s+number|count\s+of|number\s+of)\b",
    re.IGNORECASE,
)


def is_process_coverage_path(rel: str) -> bool:
    name = Path(rel.replace("\\", "/")).name.lower()
    return name in _COVERAGE_ALIASES


def normalize_process_coverage(data: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize legacy pagination_exhausted → enumeration_exhausted."""
    out = dict(data)
    if "enumeration_exhausted" not in out and "pagination_exhausted" in out:
        out["enumeration_exhausted"] = bool(out.get("pagination_exhausted"))
    if "pagination_exhausted" not in out and "enumeration_exhausted" in out:
        out["pagination_exhausted"] = bool(out.get("enumeration_exhausted"))
    return out


def validate_process_coverage(data: Mapping[str, Any]) -> list[str]:
    """Structural validation only — not truth of exhaustion."""
    violations: list[str] = []
    if not isinstance(data, Mapping):
        return ["process_coverage: root must be object"]
    has_enum = "enumeration_exhausted" in data or "pagination_exhausted" in data
    if not has_enum:
        violations.append("process_coverage: missing enumeration_exhausted or pagination_exhausted")
    pages = data.get("pages_scanned")
    if pages is not None:
        try:
            if int(pages) < 0:
                violations.append("process_coverage: pages_scanned must be >= 0")
        except (TypeError, ValueError):
            violations.append("process_coverage: pages_scanned must be integer")
    sources = data.get("sources")
    if sources is not None and not isinstance(sources, list):
        violations.append("process_coverage: sources must be array")
    note = data.get("note")
    if note is not None and not isinstance(note, str):
        violations.append("process_coverage: note must be string")
    return violations


def validate_process_coverage_file(path: Path) -> list[str]:
    if not path.is_file():
        return [f"boundary: {path.name} missing"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return [f"boundary: {path.name} invalid JSON"]
    if not isinstance(raw, dict):
        return [f"boundary: {path.name} must be JSON object"]
    return [f"boundary: {v}" for v in validate_process_coverage(raw)]


def statement_implies_enumeration(statement: str) -> bool:
    return bool(_ENUMERATION_CUE_RE.search(statement or ""))


def deliverable_is_array_retrieve(path: Path) -> bool:
    """True when JSON deliverable has array retrieved_data (RETRIEVE-style)."""
    if not path.is_file() or path.suffix.lower() != ".json":
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return False
    if not isinstance(data, dict):
        return False
    rd = data.get("retrieved_data")
    return isinstance(rd, list) and str(data.get("task_type") or "").upper() == "RETRIEVE"


def load_process_coverage(workdir: Path, rel: str) -> dict[str, Any] | None:
    path = workdir / rel
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return normalize_process_coverage(raw)


def obligations_need_enumeration_check(
    obligation_statements: Sequence[str],
    obligation_types: Mapping[str, str] | None = None,
) -> bool:
    for stmt in obligation_statements:
        if statement_implies_enumeration(stmt):
            return True
    return False
