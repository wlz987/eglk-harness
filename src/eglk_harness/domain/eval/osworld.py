"""OSWorld auxiliary thin connector (辅尺；不进 Gate)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class OsWorldTask:
    task_id: str
    instruction: str
    domain: str = ""
    notes: str = ""


def load_pack_index(eval_root: Path) -> list[OsWorldTask]:
    path = eval_root / "osworld_aux" / "pack.example.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data.get("tasks") if isinstance(data, dict) else data
    out: list[OsWorldTask] = []
    if not isinstance(tasks, list):
        return out
    for t in tasks:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "")
        if not tid:
            continue
        out.append(
            OsWorldTask(
                task_id=tid,
                instruction=str(t.get("instruction") or t.get("summary") or ""),
                domain=str(t.get("domain") or ""),
                notes=str(t.get("notes") or ""),
            )
        )
    return out


def materialize_goal(task: OsWorldTask, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    text = (
        f"# OSWorld aux · {task.task_id}\n\n"
        f"> Auxiliary desktop eval. Offline / external judge ≠ Gate input.\n\n"
        f"## Summary\n\n{task.instruction}\n\n"
        f"## Domain\n\n{task.domain or '(general)'}\n\n"
        f"## Done criteria\n\n"
        f"- [ ] Complete the desktop instruction for `{task.task_id}`\n"
        f"- [ ] Leave screenshot or file evidence under the workdir\n\n"
        f"## Notes\n\n{task.notes or 'Requires HF OSWorld access + computer-use MCP (doctor install).'}\n"
    )
    goal = out_dir / ".goal.md"
    goal.write_text(text, encoding="utf-8")
    return goal


def score_placeholder(*, task_id: str, workdir: Path) -> dict[str, Any]:
    return {
        "suite": "osworld_aux",
        "task_id": task_id,
        "judge": "external_osworld",
        "workdir": str(workdir),
        "status": "recorded_only",
        "note": "Wire OSWorldv2-harness from vendor/; never feed Gate",
        "vendor_hint": str(path_hint(workdir) or ""),
    }


def path_hint(eval_root: Path | None = None) -> Path | None:
    """Return vendor OSWorld harness path if present under eval_root or alw."""
    roots: list[Path] = []
    if eval_root is not None:
        roots.append(Path(eval_root))
        roots.append(Path(eval_root).parent)  # experiment/
        roots.append(Path(eval_root).parents[1] if len(Path(eval_root).parents) > 1 else Path(eval_root))
    here = Path(__file__).resolve()
    # .../alw/eglk-harness/src/eglk_harness/domain/eval/osworld.py → alw
    if len(here.parents) > 5:
        roots.append(here.parents[5])
    seen: set[Path] = set()
    for root in roots:
        root = root.resolve()
        if root in seen:
            continue
        seen.add(root)
        for cand in (
            root / "experiment" / "eval" / "vendor" / "OSWorldv2-harness",
            root / "eval" / "vendor" / "OSWorldv2-harness",
            root / "vendor" / "OSWorldv2-harness",
        ):
            if cand.is_dir():
                return cand
    return None
