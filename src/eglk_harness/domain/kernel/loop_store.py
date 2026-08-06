"""Loop artifact IO under ``.eglk-harness/loop/<goal_id>/``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.tree import TaskTree


def ensure_loop_layout(workdir: Path, goal_id: str) -> Path:
    """Create claims/evidence/decisions/candidates/sigma/refined/world dirs."""
    root = paths.loop_goal_dir(workdir, goal_id)
    for name in (
        "claims",
        "evidence",
        "decisions",
        "candidates",
        "world",
        "sigma",
        "sigma/refined",
    ):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: Mapping[str, Any] | list[Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def tree_path(loop_dir: Path) -> Path:
    return loop_dir / "subgoals_tree.json"


def save_tree(loop_dir: Path, tree: TaskTree) -> Path:
    return write_json(tree_path(loop_dir), tree.to_document())


def load_tree(loop_dir: Path) -> TaskTree | None:
    p = tree_path(loop_dir)
    if not p.is_file():
        return None
    return TaskTree.from_document(read_json(p))


def write_claim(loop_dir: Path, tick: int, claim: Mapping[str, Any]) -> Path:
    return write_json(loop_dir / "claims" / f"{tick:03d}.json", dict(claim))


def write_evidence(loop_dir: Path, tick: int, evidence: Mapping[str, Any]) -> Path:
    return write_json(loop_dir / "evidence" / f"{tick:03d}.json", dict(evidence))


def write_decision(loop_dir: Path, tick: int, decision: Mapping[str, Any]) -> Path:
    return write_json(loop_dir / "decisions" / f"{tick:03d}.json", dict(decision))


def world_pre_dir(loop_dir: Path, tick: int) -> Path:
    return loop_dir / "world" / f"pre_{tick:03d}"
