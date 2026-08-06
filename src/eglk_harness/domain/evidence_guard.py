"""Normalize Checker Evidence before Gate — truth-blind, not a second Gate."""

from __future__ import annotations

from typing import Any

_FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {"score", "oracle", "pass_rate", "wa_score", "benchmark", "ground_truth"}
)


def normalize_evidence(
    doc: dict[str, Any],
    *,
    written: list[str] | None = None,
    mutations: list[str] | None = None,
) -> dict[str, Any]:
    """Strip oracle/scorer keys; ensure gaps; hint artifacts vs written."""
    written = written or []
    mutations = mutations or []
    out = {k: v for k, v in doc.items() if k not in _FORBIDDEN_EVIDENCE_KEYS}
    if "gaps" not in out or out["gaps"] is None:
        out["gaps"] = []
    if not isinstance(out["gaps"], list):
        out["gaps"] = [str(out["gaps"])]
    artifacts = out.get("artifacts")
    if artifacts is None:
        out["artifacts"] = list(written)
    elif isinstance(artifacts, list) and not artifacts and written:
        # Soft align: empty artifacts with known writes → use written paths
        out["artifacts"] = list(written)
    # Preserve integrity_violation if fingerprint layer already set it
    if mutations and out.get("integrity_violation") is None:
        # Do not invent integrity_violation; Gate/fingerprint owns that.
        pass
    return out
