"""Repair-count aggregation for Gate REPAIRS_MAX (per obligation_id + reason)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

_CLOSURE_OBLIGATION_ID = "__closure__"


def repair_count_key(obligation_id: str, reason: str) -> str:
    """SSOT key for quota.repair_counts (see design/kernel/schemas/quota.schema.json)."""
    oid = str(obligation_id or "__all__").strip() or "__all__"
    r = str(reason or "incomplete").strip() or "incomplete"
    return f"{oid}:{r}"


def closure_repair_key() -> str:
    return repair_count_key(_CLOSURE_OBLIGATION_ID, "closure_incomplete")


def repair_key_from_gate_payload(payload: Mapping[str, Any]) -> str:
    """Derive repair_counts key from a GateDecided payload."""
    reason = str(payload.get("reason") or "incomplete")
    if reason == "closure_incomplete":
        return closure_repair_key()
    open_ids = payload.get("open_obligation_ids") or []
    if isinstance(open_ids, list) and open_ids:
        return repair_count_key(str(open_ids[0]), reason)
    return repair_count_key("__all__", reason)


def repair_counts_from_decisions(loop_dir: Path, *, subgoal_id: str | None = None) -> dict[str, int]:
    """Count prior ``repair`` GateDecided events by repair_count_key (legacy decisions/*.json fallback)."""
    counts: dict[str, int] = {}
    dec = loop_dir / "decisions"
    if dec.is_dir():
        for path in sorted(dec.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or data.get("decision") != "repair":
                continue
            if subgoal_id and data.get("subgoal_id") and str(data.get("subgoal_id")) != subgoal_id:
                continue
            key = repair_key_from_gate_payload(data)
            counts[key] = int(counts.get(key, 0)) + 1
    return counts


def load_runtime_state(loop_dir: Path, *, workdir: Path | None = None) -> dict[str, Any]:
    """Diagnostic runtime signals from run_projection (events SSOT)."""
    from eglk_harness.domain.kernel.projection_read import hydrate_runtime_signals, read_last_tick_record

    goal_id = loop_dir.name
    wd = workdir if workdir is not None else loop_dir.parent.parent.parent
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
