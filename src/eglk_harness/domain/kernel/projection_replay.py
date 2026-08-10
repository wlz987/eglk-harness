"""Rebuild projections from EventStore — design invariant 7."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eglk_harness.domain.event_store import open_store
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.reducer import (
    ProjectionState,
    obligation_ledger_dict,
    reduce_events,
    run_projection_dict,
    task_structure_dict,
)


def rebuild_from_events(loop_dir: Path) -> dict[str, Any]:
    """Pure replay: events.db → projection dicts."""
    store = open_store(loop_dir)
    try:
        state = reduce_events(store.read_all())
    finally:
        store.close()
    return {
        "run": run_projection_dict(state),
        "task_structure": task_structure_dict(state),
        "obligation_ledger": obligation_ledger_dict(state),
        "repair_counts": dict(state.repair_counts),
        "last_gate": state.last_gate,
    }


def write_projection_cache(workdir: Path, goal_id: str, exported: dict[str, Any]) -> Path:
    proj_dir = paths.projections_dir(workdir, goal_id)
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "run_projection.json").write_text(
        json.dumps(exported["run"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if exported.get("task_structure"):
        (proj_dir / "task_structure.json").write_text(
            json.dumps(exported["task_structure"], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if exported.get("obligation_ledger"):
        (proj_dir / "obligation_ledger.json").write_text(
            json.dumps(exported["obligation_ledger"], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return proj_dir


def replay_workdir(workdir: Path, goal_id: str) -> dict[str, Any]:
    loop_dir = paths.loop_goal_dir(workdir, goal_id)
    exported = rebuild_from_events(loop_dir)
    write_projection_cache(workdir, goal_id, exported)
    return exported


def projection_diff(a: Any, b: Any) -> list[str]:
    """Shallow structural diff for replay equivalence tests."""
    if a == b:
        return []
    if type(a) != type(b):
        return [f"type_mismatch:{type(a).__name__}!={type(b).__name__}"]
    if isinstance(a, dict):
        diffs: list[str] = []
        keys = set(a.keys()) | set(b.keys())
        for k in sorted(keys):
            if k not in a:
                diffs.append(f"missing_left:{k}")
            elif k not in b:
                diffs.append(f"missing_right:{k}")
            else:
                sub = projection_diff(a[k], b[k])
                diffs.extend(f"{k}.{s}" for s in sub)
        return diffs
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"list_len:{len(a)}!={len(b)}"]
        diffs: list[str] = []
        for i, (x, y) in enumerate(zip(a, b)):
            sub = projection_diff(x, y)
            diffs.extend(f"[{i}].{s}" for s in sub)
        return diffs
    return [f"value:{a!r}!={b!r}"]


def projection_state_from_loop(loop_dir: Path) -> ProjectionState:
    """Replay events.db → ProjectionState (read-only; for sidecar advisors)."""
    store = open_store(loop_dir)
    try:
        return reduce_events(store.read_all())
    finally:
        store.close()
