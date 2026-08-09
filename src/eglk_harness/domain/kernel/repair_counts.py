"""Repair-count aggregation for Gate REPAIRS_MAX (per reason)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def repair_counts_from_decisions(loop_dir: Path, *, subgoal_id: str | None = None) -> dict[str, int]:
    """Count prior ``repair`` decisions by reason (optionally filtered by leaf)."""
    dec = loop_dir / "decisions"
    if not dec.is_dir():
        return {}
    counts: dict[str, int] = {}
    for path in sorted(dec.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("decision") != "repair":
            continue
        if subgoal_id and str(data.get("subgoal_id") or "") not in {subgoal_id, ""}:
            # count only same leaf when id present on both sides
            if data.get("subgoal_id") and str(data.get("subgoal_id")) != subgoal_id:
                continue
        reason = str(data.get("reason") or "incomplete")
        counts[reason] = int(counts.get(reason, 0)) + 1
    return counts

def load_runtime_state(loop_dir: Path, *, workdir: Path | None = None) -> dict[str, Any]:
    """Diagnostic runtime signals from run_projection + ticks.jsonl (not SSOT)."""
    from eglk_harness.domain.kernel.projection_read import hydrate_runtime_signals, read_last_tick_record

    goal_id = loop_dir.name
    wd = workdir
    if wd is None:
        wd = loop_dir.parent.parent.parent
    quota, focus, uncertainty = hydrate_runtime_signals({}, loop_dir, wd, goal_id)
    tick_rec = read_last_tick_record(loop_dir)
    out: dict[str, Any] = {"quota": quota}
    if focus is not None:
        out["focus_score"] = focus
    if uncertainty is not None:
        out["uncertainty"] = uncertainty
    if tick_rec and tick_rec.get("tick") is not None:
        try:
            out["tick"] = int(tick_rec["tick"])
        except (TypeError, ValueError):
            pass
    return out
