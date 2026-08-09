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
    """Strip oracle/scorer keys; ensure verdicts / additional_gaps shape."""
    written = written or []
    mutations = mutations or []
    out = {k: v for k, v in doc.items() if k not in _FORBIDDEN_EVIDENCE_KEYS}

    # Preserve 0.2.x keys long enough for coerce_document to lift them.
    if "gaps" not in out or out["gaps"] is None:
        out["gaps"] = []
    if not isinstance(out["gaps"], list):
        out["gaps"] = [str(out["gaps"])]

    if "additional_gaps" not in out or out["additional_gaps"] is None:
        # Lift boundary:* gaps early when already present
        out["additional_gaps"] = [
            str(g) for g in out["gaps"] if str(g).startswith("boundary:")
        ]
    elif not isinstance(out["additional_gaps"], list):
        out["additional_gaps"] = [str(out["additional_gaps"])]

    artifacts = out.get("artifacts")
    if artifacts is None and written:
        out["artifacts"] = list(written)
    elif isinstance(artifacts, list) and not artifacts and written:
        out["artifacts"] = list(written)

    if mutations and out.get("integrity_violation") is None:
        pass

    if workdir is not None and boundary:
        from eglk_harness.domain.runtime.boundary_verify import (
            apply_boundary_to_evidence,
            verify_boundary,
        )

        out = apply_boundary_to_evidence(out, workdir=workdir, boundary=boundary)
        violations = verify_boundary(workdir, boundary)
        if violations:
            return out
        gaps = [str(g) for g in (out.get("gaps") or []) if str(g).strip()]
        challenges = [str(c) for c in (out.get("challenges") or []) if str(c).strip()]
        if challenges and not gaps:
            arts = list(out.get("artifacts") or [])
            for c in challenges:
                tag = f"[methodology] {c}"
                if tag not in arts:
                    arts.append(tag)
            out["artifacts"] = arts
            out["challenges"] = []
    return out


def align_claim_delivery_progress(
    claim: Mapping[str, Any],
    *,
    workdir: Path,
    boundary: list[str] | None,
) -> dict[str, Any]:
    """Mechanically align Maker self_assessment telemetry with on-disk boundary.

    Diagnostic only — Gate never reads self_assessment / done_progress.
    """
    out = dict(claim)
    if not boundary:
        return out
    from eglk_harness.domain.runtime.boundary_verify import verify_boundary

    violations = verify_boundary(workdir, boundary)
    sa = out.get("self_assessment") if isinstance(out.get("self_assessment"), dict) else {}
    try:
        done = float(sa.get("done_progress", out.get("done_progress", 0)) or 0)
    except (TypeError, ValueError):
        done = 0.0
    if violations:
        done = min(done, 0.45)
    elif done < 1.0:
        done = 1.0
    conf = 0.0
    try:
        conf = float(sa.get("confidence", out.get("confidence", 0)) or 0)
    except (TypeError, ValueError):
        conf = 0.0
    out["self_assessment"] = {"done_progress": done, "confidence": max(0.0, min(1.0, conf))}
    out.pop("done_progress", None)
    out.pop("confidence", None)
    return out
