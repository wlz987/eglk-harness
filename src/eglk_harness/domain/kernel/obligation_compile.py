"""Coarse-first Obligation compilation from goal criteria (correctness over fake precision).

See design/kernel/semantic_core.md §2.4.
"""

from __future__ import annotations

import re
from eglk_harness.domain.kernel.goal_parse import INTENT_CRITERIA_FALLBACK

VERIFICATION_TYPES = frozenset(
    {
        "file_exists",
        "file_content_match",
        "command_exit",
        "api_state",
        "structured_diff",
        "custom_attestation",
    }
)

_EXPLICIT_EXISTS = re.compile(
    r"\bMUST_EXIST\b|"
    r"(?:must|should)\s+(?:exist|be\s+present)\b|"
    r"(?:file|path)\s+[`'\"]?[\w./\-]+\.(?:txt|json|har|md|yaml|yml)[`'\"]?\s+(?:must|shall)\s+exist",
    re.IGNORECASE,
)
_EXPLICIT_PATH = re.compile(
    r"(?:^|[\s`\"'])(/[\w./\-]+\.\w{1,8}|[\w\-]+/[\w./\-]+\.\w{1,8}|[\w./\-]+\.\w{1,8})(?:$|[\s`\"'])",
)


def choose_root_verification_type(statement: str) -> str:
    """Prefer conservative custom_attestation unless the statement clearly requires file existence.

    Never invent file_content_match / api_state without concrete observable binding.
    """
    s = (statement or "").strip()
    if not s:
        return "custom_attestation"
    if re.search(r"\bMUST_EXIST\b", s, re.IGNORECASE):
        return "file_exists"
    if re.search(r"(?:must|should)\s+(?:exist|be\s+present)\b", s, re.IGNORECASE):
        if _EXPLICIT_PATH.search(s):
            return "file_exists"
    if _EXPLICIT_EXISTS.search(s) and _EXPLICIT_PATH.search(s):
        return "file_exists"
    return "custom_attestation"


def compile_root_obligations(
    criteria: Sequence[str],
    *,
    requirement_id: str = "req-1",
    id_prefix: str = "ob",
) -> list[dict[str, Any]]:
    """Intent-level root obligations — macroscopic, conservative verification_type."""
    out: list[dict[str, Any]] = []
    items = [str(c).strip() for c in criteria if str(c).strip()]
    if not items:
        items = [INTENT_CRITERIA_FALLBACK]
    for i, statement in enumerate(items, start=1):
        out.append(
            {
                "id": f"{id_prefix}-{i}",
                "requirement_id": requirement_id,
                "parent_obligation_id": None,
                "statement": statement,
                "verification_type": choose_root_verification_type(statement),
                "status": "open",
                "origin": "root",
            }
        )
    return out


def propose_derived_obligation(
    *,
    parent_id: str,
    requirement_id: str,
    statement: str,
    verification_type: str = "custom_attestation",
    derived_id: str,
    derivation_ref: str | None = None,
) -> dict[str, Any]:
    """Build a derived obligation dict (Amendment/split candidate payload)."""
    vt = verification_type if verification_type in VERIFICATION_TYPES else "custom_attestation"
    return {
        "id": derived_id,
        "requirement_id": requirement_id,
        "parent_obligation_id": parent_id,
        "statement": statement,
        "verification_type": vt,
        "status": "open",
        "origin": "derived",
        "derivation_ref": derivation_ref,
    }
