"""WA-Hard thin connector (主尺入口；不进 Gate)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class WaHardTask:
    task_id: str
    intent: str
    sites: list[str]
    notes: str = ""


def load_pack_index(eval_root: Path) -> list[WaHardTask]:
    """Load ``wa_hard/pack.example.json`` if present."""
    path = eval_root / "wa_hard" / "pack.example.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data.get("tasks") if isinstance(data, dict) else data
    out: list[WaHardTask] = []
    if not isinstance(tasks, list):
        return out
    for t in tasks:
        if not isinstance(t, dict):
            continue
        out.append(
            WaHardTask(
                task_id=str(t.get("id") or ""),
                intent=str(t.get("intent") or t.get("summary") or ""),
                sites=[str(s) for s in (t.get("sites") or [])],
                notes=str(t.get("notes") or ""),
            )
        )
    return [t for t in out if t.task_id]


def materialize_goal(task: WaHardTask, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    sites = ", ".join(task.sites) if task.sites else "(unspecified)"
    text = (
        f"# WA-Hard · {task.task_id}\n\n"
        f"> Primary eval pack (WebArena-Verified Hard). Offline judge ≠ Gate input.\n\n"
        f"## Summary\n\n{task.intent}\n\n"
        f"## Sites\n\n{sites}\n\n"
        f"## Done criteria\n\n"
        f"- [ ] Satisfy the WA-Hard intent for `{task.task_id}`\n"
        f"- [ ] Leave inspectable artifacts proving completion\n\n"
        f"## Notes\n\n{task.notes or '(none)'}\n"
    )
    goal = out_dir / ".goal.md"
    goal.write_text(text, encoding="utf-8")
    return goal


def score_placeholder(*, task_id: str, workdir: Path) -> dict[str, Any]:
    """Record that a run happened; real WA-Verified judge is external."""
    return {
        "suite": "wa_hard",
        "task_id": task_id,
        "judge": "external_wa_verified",
        "workdir": str(workdir),
        "status": "recorded_only",
        "note": "Wire ServiceNow/webarena-verified harness separately; never feed Gate",
    }
