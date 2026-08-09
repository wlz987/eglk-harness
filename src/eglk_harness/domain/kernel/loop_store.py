"""Loop artifact IO under ``.eglk-harness/loop/<goal_id>/`` — projections from events only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.tree import TaskTree


def ensure_loop_layout(workdir: Path, goal_id: str) -> Path:
    """Delegate to kernel paths — no claims/evidence/decisions authority dirs."""
    return paths.ensure_loop_layout(workdir, goal_id)


def write_json(path: Path, data: Mapping[str, Any] | list[Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def tree_path(loop_dir: Path) -> Path:
    return loop_dir / "projections" / "task_structure.json"


def load_tree(loop_dir: Path) -> TaskTree | None:
    p = tree_path(loop_dir)
    if not p.is_file():
        return None
    return TaskTree.from_document(read_json(p))


def world_pre_dir(loop_dir: Path, tick: int) -> Path:
    return loop_dir / "world" / f"pre_{tick:03d}"


def events_db(loop_dir: Path) -> Path:
    return loop_dir / "events.db"
