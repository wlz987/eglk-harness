"""Loop artifact IO under ``.eglk-harness/loop/<goal_id>/`` (projections + legacy helpers)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.tree import TaskTree


def ensure_loop_layout(workdir: Path, goal_id: str) -> Path:
    """Create loop dirs (+ transitional claims/evidence/decisions for tick)."""
    root = paths.ensure_loop_layout(workdir, goal_id)
    # Transitional tick still writes these; EventStore is authority.
    for name in ("claims", "evidence", "decisions"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: Mapping[str, Any] | list[Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def tree_path(loop_dir: Path) -> Path:
    # Prefer task_structure projection; fall back to legacy filename
    modern = loop_dir / "projections" / "task_structure.json"
    if modern.is_file():
        return modern
    return loop_dir / "subgoals_tree.json"


def save_tree(loop_dir: Path, tree: TaskTree) -> Path:
    # Dual-write during transition
    write_json(loop_dir / "subgoals_tree.json", tree.to_document())
    return write_json(loop_dir / "projections" / "task_structure.json", tree.to_document())


def load_tree(loop_dir: Path) -> TaskTree | None:
    p = tree_path(loop_dir)
    if not p.is_file():
        legacy = loop_dir / "subgoals_tree.json"
        if not legacy.is_file():
            return None
        p = legacy
    return TaskTree.from_document(read_json(p))


def write_claim(loop_dir: Path, tick: int, claim: Mapping[str, Any]) -> Path:
    return write_json(loop_dir / "claims" / f"{tick:03d}.json", dict(claim))


def write_evidence(loop_dir: Path, tick: int, evidence: Mapping[str, Any]) -> Path:
    return write_json(loop_dir / "evidence" / f"{tick:03d}.json", dict(evidence))


def write_decision(loop_dir: Path, tick: int, decision: Mapping[str, Any]) -> Path:
    return write_json(loop_dir / "decisions" / f"{tick:03d}.json", dict(decision))


def world_pre_dir(loop_dir: Path, tick: int) -> Path:
    return loop_dir / "world" / f"pre_{tick:03d}"


def events_db(loop_dir: Path) -> Path:
    return loop_dir / "events.db"
