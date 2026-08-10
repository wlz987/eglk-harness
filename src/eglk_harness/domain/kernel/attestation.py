"""Mechanical Attestation floor — no LLM, no Oracle.

See design/kernel/semantic_core.md §6 and gate_policy.md evidence floor.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from pathlib import Path

ATTESTATION_METHODS = frozenset(
    {
        "file_exists",
        "file_content_match",
        "command_exit",
        "api_state",
        "structured_diff",
        "custom_attestation",
    }
)

# Hard verification_type → allowed attestation methods (custom always allowed as fallback).
_TYPE_ALLOWED: dict[str, frozenset[str]] = {
    "file_exists": frozenset({"file_exists", "custom_attestation"}),
    "file_content_match": frozenset({"file_content_match", "file_exists", "custom_attestation"}),
    "command_exit": frozenset({"command_exit", "custom_attestation"}),
    "api_state": frozenset({"api_state", "custom_attestation"}),
    "structured_diff": frozenset({"structured_diff", "custom_attestation"}),
    "custom_attestation": ATTESTATION_METHODS,
}


def _as_list(x: Any) -> list[Any]:
    return list(x) if isinstance(x, (list, tuple)) else []


def attestation_structurally_valid(
    att: Mapping[str, Any],
    *,
    expected_world_revision: int | None = None,
) -> bool:
    """Required fields + method enum + optional world_revision bind."""
    if not isinstance(att, Mapping):
        return False
    method = str(att.get("method") or "").strip()
    if method not in ATTESTATION_METHODS:
        return False
    if not str(att.get("digest") or "").strip():
        return False
    if not str(att.get("observer") or "").strip():
        return False
    if not str(att.get("raw_ref") or "").strip():
        return False
    if "world_revision" not in att:
        return False
    try:
        rev = int(att["world_revision"])
    except (TypeError, ValueError):
        return False
    if rev < 0:
        return False
    if expected_world_revision is not None and rev != int(expected_world_revision):
        return False
    watch = att.get("watch_set")
    if watch is not None and not isinstance(watch, (list, tuple)):
        return False
    return True


def method_allowed_for_verification_type(method: str, verification_type: str | None) -> bool:
    """When obligation type is known, method must be in the allowed set."""
    if not verification_type:
        return method in ATTESTATION_METHODS
    allowed = _TYPE_ALLOWED.get(str(verification_type), ATTESTATION_METHODS)
    return method in allowed


def attestation_valid_for_obligation(
    att: Mapping[str, Any],
    *,
    verification_type: str | None = None,
    expected_world_revision: int | None = None,
) -> bool:
    if not attestation_structurally_valid(att, expected_world_revision=expected_world_revision):
        return False
    method = str(att.get("method") or "")
    return method_allowed_for_verification_type(method, verification_type)


def digest_matches_workdir(workdir: Path, att: Mapping[str, Any]) -> bool:
    """Recompute sha256 for ``raw_ref`` when digest claims a file hash."""
    from pathlib import Path as _Path

    import hashlib as _hashlib

    digest = str(att.get("digest") or "")
    raw = str(att.get("raw_ref") or "").strip().lstrip("/")
    if not raw or not digest.startswith("sha256:"):
        return True
    path = _Path(workdir) / raw
    if not path.is_file():
        return digest == "missing"
    got = "sha256:" + _hashlib.sha256(path.read_bytes()).hexdigest()
    return got == digest


def verdict_has_valid_attestation(
    verdict: Mapping[str, Any],
    *,
    verification_type: str | None = None,
    expected_world_revision: int | None = None,
) -> bool:
    for a in _as_list(verdict.get("attestations")):
        if isinstance(a, Mapping) and attestation_valid_for_obligation(
            a,
            verification_type=verification_type,
            expected_world_revision=expected_world_revision,
        ):
            return True
    return False


def obligation_type_map(contract: Mapping[str, Any] | None) -> dict[str, str]:
    """Optional ``obligation_verification_types`` on WorkContract (id → type)."""
    if not isinstance(contract, Mapping):
        return {}
    raw = contract.get("obligation_verification_types")
    if not isinstance(raw, Mapping):
        return {}
    return {str(k): str(v) for k, v in raw.items() if str(k) and str(v)}
