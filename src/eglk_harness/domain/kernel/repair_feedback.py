"""Repair → next WorkContract feedback (gaps / unsatisfied reasons).

Mechanical extraction only — never reads eval scorers.
See design/kernel/semantic_core.md §3 and multi_agent.md WorkContract injection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def _as_list(x: Any) -> list[Any]:
    return list(x) if isinstance(x, (list, tuple)) else []


def extract_repair_feedback(
    *,
    evidence: Mapping[str, Any] | None,
    decision: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Build ``repair_feedback`` when prior Gate decision was repair."""
    if not isinstance(decision, Mapping):
        return None
    if str(decision.get("decision") or "") != "repair":
        return None
    reason = str(decision.get("reason") or "no_attestation")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    unsatisfied: list[str] = []
    gaps: list[str] = []
    defect_ids: list[str] = []
    for v in _as_list(evidence.get("verdicts")):
        if not isinstance(v, Mapping):
            continue
        oid = str(v.get("obligation_id") or "")
        status = str(v.get("status") or "")
        if status != "satisfied":
            if oid:
                unsatisfied.append(oid)
            for g in _as_list(v.get("gaps")):
                gs = str(g).strip()
                if gs and gs not in gaps:
                    gaps.append(gs)
        if v.get("defect_suspected") is True and oid:
            defect_ids.append(oid)
    # Prefer Gate open_obligation_ids when present
    open_ids = [str(x) for x in _as_list(decision.get("open_obligation_ids")) if str(x)]
    if open_ids:
        unsatisfied = open_ids
    additional = [str(g) for g in _as_list(evidence.get("additional_gaps")) if str(g).strip()]
    return {
        "prior_decision": "repair",
        "reason": reason,
        "unsatisfied_obligation_ids": unsatisfied,
        "gaps": gaps,
        "additional_gaps": additional,
        "defect_suspected_obligation_ids": defect_ids,
    }


def load_prior_repair_feedback(loop_dir: Path, *, current_tick: int) -> dict[str, Any] | None:
    """Load feedback iff the immediately previous tick Gate decision was repair."""
    if current_tick <= 0:
        return None
    tick = current_tick - 1
    dpath = loop_dir / "decisions" / f"{tick:03d}.json"
    if not dpath.is_file():
        return None
    try:
        decision = json.loads(dpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(decision, dict) or str(decision.get("decision") or "") != "repair":
        return None
    evidence: Mapping[str, Any] | None = None
    epath = loop_dir / "evidence" / f"{tick:03d}.json"
    if epath.is_file():
        try:
            raw = json.loads(epath.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                evidence = raw
        except (OSError, json.JSONDecodeError):
            evidence = None
    return extract_repair_feedback(evidence=evidence, decision=decision)


def repair_feedback_as_prior_evidence(feedback: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expand repair_feedback into LeafContract prior_evidence entries (Maker sees full text)."""
    out: list[dict[str, Any]] = []
    reason = str(feedback.get("reason") or "")
    out.append(
        {
            "kind": "repair_feedback",
            "ref": "gate",
            "text": f"prior Gate repair: {reason}",
        }
    )
    for oid in _as_list(feedback.get("unsatisfied_obligation_ids")):
        out.append({"kind": "unsatisfied_obligation", "ref": str(oid), "text": f"open: {oid}"})
    for g in _as_list(feedback.get("gaps")):
        out.append({"kind": "gap", "ref": "verdict", "text": str(g)})
    for g in _as_list(feedback.get("additional_gaps")):
        out.append({"kind": "additional_gap", "ref": "boundary", "text": str(g)})
    for oid in _as_list(feedback.get("defect_suspected_obligation_ids")):
        out.append(
            {
                "kind": "defect_suspected",
                "ref": str(oid),
                "text": f"defect_suspected: {oid}",
            }
        )
    return out


def render_repair_feedback_block(feedback: Mapping[str, Any], *, titles_only: bool = False) -> str:
    """Prompt block for Maker (full) or Checker (titles)."""
    lines = ["[REPAIR_FEEDBACK]", f"reason: {feedback.get('reason')}"]
    unsat = _as_list(feedback.get("unsatisfied_obligation_ids"))
    lines.append("unsatisfied_obligation_ids:")
    if unsat:
        lines.extend(f"  - {x}" for x in unsat)
    else:
        lines.append("  - (none)")
    if titles_only:
        gaps = _as_list(feedback.get("gaps"))
        lines.append(f"gaps_count: {len(gaps)}")
        for g in gaps[:5]:
            lines.append(f"  - {str(g)[:80]}")
        return "\n".join(lines)
    lines.append("gaps:")
    gaps = _as_list(feedback.get("gaps"))
    if gaps:
        lines.extend(f"  - {g}" for g in gaps)
    else:
        lines.append("  - (none)")
    lines.append("additional_gaps:")
    add = _as_list(feedback.get("additional_gaps"))
    if add:
        lines.extend(f"  - {g}" for g in add)
    else:
        lines.append("  - (none)")
    return "\n".join(lines)
