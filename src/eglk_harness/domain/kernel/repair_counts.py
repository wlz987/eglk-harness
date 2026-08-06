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


def load_runtime_state(loop_dir: Path) -> dict[str, Any]:
    path = loop_dir / "state.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
