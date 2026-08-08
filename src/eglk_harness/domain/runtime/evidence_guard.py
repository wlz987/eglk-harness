"""Normalize Checker Evidence before Gate — truth-blind, not a second Gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

_FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {"score", "oracle", "pass_rate", "wa_score", "benchmark", "ground_truth"}
)


def normalize_evidence(
    doc: dict[str, Any],
    *,
    written: list[str] | None = None,
    mutations: list[str] | None = None,
    workdir: Path | None = None,
    boundary: list[str] | None = None,
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
    if workdir is not None and boundary:
        from eglk_harness.domain.runtime.boundary_verify import (
            apply_boundary_to_evidence,
            verify_boundary,
        )

        out = apply_boundary_to_evidence(out, workdir=workdir, boundary=boundary)
        if not verify_boundary(workdir, boundary):
            gaps = [str(g) for g in (out.get("gaps") or []) if str(g).strip()]
            try:
                audit = float(out.get("audit_progress", 0))
            except (TypeError, ValueError):
                audit = 0.0
            if not gaps and audit < 1.0:
                out["audit_progress"] = 1.0
            challenges = [str(c) for c in (out.get("challenges") or []) if str(c).strip()]
            if challenges and not gaps:
                artifacts = list(out.get("artifacts") or [])
                for c in challenges:
                    tag = f"[methodology] {c}"
                    if tag not in artifacts:
                        artifacts.append(tag)
                out["artifacts"] = artifacts
                out["challenges"] = []
    return out


def align_claim_delivery_progress(
    claim: Mapping[str, Any],
    *,
    workdir: Path,
    boundary: list[str] | None,
) -> dict[str, Any]:
    """Mechanically align Maker done_progress when delivery boundary is satisfied on disk."""
    out = dict(claim)
    if not boundary:
        return out
    from eglk_harness.domain.runtime.boundary_verify import verify_boundary

    if verify_boundary(workdir, boundary):
        return out
    try:
        done = float(out.get("done_progress", 0))
    except (TypeError, ValueError):
        done = 0.0
    if done < 1.0:
        out["done_progress"] = 1.0
    return out
