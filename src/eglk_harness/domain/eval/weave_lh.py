"""Weave LH auxiliary connector — LH WeaveBench-harness shaped; never Gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class WeaveLhTask:
    task_id: str
    summary: str
    notes: str = ""


def discover_vendor(eval_root: Path | None = None) -> Path | None:
    """Return WeaveBench-harness path under vendor or reference."""
    roots: list[Path] = []
    if eval_root is not None:
        er = Path(eval_root)
        roots.extend(
            [
                er / "vendor" / "LongHorizon-Harness" / "eval" / "WeaveBench-harness",
                er / "vendor" / "WeaveBench-harness",
            ]
        )
    here = Path(__file__).resolve()
    if len(here.parents) > 5:
        alw = here.parents[5]
        roots.extend(
            [
                alw / "experiment" / "eval" / "vendor" / "LongHorizon-Harness" / "eval" / "WeaveBench-harness",
                alw / "reference" / "LongHorizon-Harness" / "eval" / "WeaveBench-harness",
            ]
        )
    for cand in roots:
        if cand.is_dir() and any(cand.iterdir()):
            return cand
    return None


def vendor_status(eval_root: Path | None = None) -> dict[str, Any]:
    root = discover_vendor(eval_root)
    n = 0
    if root is not None:
        n = sum(1 for _ in root.rglob("*") if _.is_file())
    return {
        "vendor_path": str(root) if root else None,
        "vendor_ready": root is not None and n >= 5,
        "file_count": n,
        "note": "scores never feed Gate; skip live Weave when not vendor_ready",
    }


def load_pack_index(eval_root: Path) -> list[WeaveLhTask]:
    """Prefer weave_lh/pack.json, else pack.example.json, else synthesize from fixtures."""
    pack = Path(eval_root) / "weave_lh" / "pack.json"
    if not pack.is_file():
        pack = Path(eval_root) / "weave_lh" / "pack.example.json"
    out: list[WeaveLhTask] = []
    if pack.is_file():
        data = json.loads(pack.read_text(encoding="utf-8"))
        tasks = data.get("tasks") if isinstance(data, dict) else data
        if isinstance(tasks, list):
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                tid = str(t.get("id") or "")
                if not tid:
                    continue
                out.append(
                    WeaveLhTask(
                        task_id=tid,
                        summary=str(t.get("summary") or t.get("instruction") or ""),
                        notes=str(t.get("notes") or ""),
                    )
                )
    return out


def list_tasks(eval_root: Path, *, limit: int | None = None) -> list[WeaveLhTask]:
    tasks = load_pack_index(eval_root)
    if limit is not None:
        tasks = tasks[: max(0, int(limit))]
    return tasks


def materialize_goal(task: WeaveLhTask, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    text = (
        f"# Weave LH · {task.task_id}\n\n"
        f"> Auxiliary WeaveBench-shaped task (LH eval method). "
        f"Offline judge ≠ Gate input.\n\n"
        f"## Summary\n\n{task.summary or task.task_id}\n\n"
        f"## Done criteria\n\n"
        f"- [ ] Satisfy the Weave task intent for `{task.task_id}`\n"
        f"- [ ] Leave inspectable artifacts for the offline judge\n\n"
        f"## Notes\n\n{task.notes or 'Scores are Manifest-only — never Gate.'}\n"
    )
    goal = out_dir / ".goal.md"
    goal.write_text(text, encoding="utf-8")
    return goal


def score_from_judge_result(result_json: Path) -> dict[str, Any]:
    """Read LH/Weave-style judge JSON into Manifest-safe scores."""
    path = Path(result_json)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"judge result must be a JSON object: {path}")
    scores = data.get("scores") if isinstance(data.get("scores"), dict) else data
    out = {str(k): v for k, v in scores.items()}
    out.setdefault("judge", "weave_lh_external")
    out.setdefault("source", str(path))
    out["status"] = "external_scored"
    out["suite"] = "weave_lh"
    out.pop("admit", None)
    out.pop("gate", None)
    return out


def score_placeholder(*, task_id: str, workdir: Path, eval_root: Path | None = None) -> dict[str, Any]:
    st = vendor_status(eval_root)
    return {
        "suite": "weave_lh",
        "task_id": task_id,
        "judge": "weave_lh",
        "workdir": str(workdir),
        "status": "vendor_skipped" if not st["vendor_ready"] else "recorded_only",
        "vendor": st,
        "note": "Wire LH WeaveBench judge externally; never feed Gate",
    }
