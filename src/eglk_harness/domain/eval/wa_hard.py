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
    """Load ``wa_hard/pack.json`` if present, else ``pack.example.json``."""
    root = Path(eval_root) / "wa_hard"
    path = root / "pack.json"
    if not path.is_file():
        path = root / "pack.example.json"
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


def score_external(result_json: Path) -> dict[str, Any]:
    """Read an external WA-Hard judge JSON into a Manifest-safe scores dict.

    Never feeds Gate. Accepts either a flat scores object or ``{scores: {...}}``.
    """
    data = json.loads(result_json.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"external score must be a JSON object: {result_json}")
    scores = data.get("scores") if isinstance(data.get("scores"), dict) else data
    out = {str(k): v for k, v in scores.items()}
    out.setdefault("judge", "external_wa_verified")
    out.setdefault("source", str(result_json))
    out["status"] = "external_scored"
    # Strip anything that looks like Gate input
    out.pop("admit", None)
    out.pop("gate", None)
    return out


def run_batch(
    eval_root: Path,
    *,
    out_root: Path,
    limit: int | None = None,
    prepare_only: bool = True,
    external_score_dir: Path | None = None,
) -> dict[str, Any]:
    """Prepare (and optionally score) a batch of WA-Hard tasks. Scores never feed Gate."""
    tasks = load_pack_index(eval_root)
    if limit is not None:
        tasks = tasks[: max(0, int(limit))]
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for task in tasks:
        task_dir = out_root / task.task_id
        materialize_goal(task, task_dir)
        from eglk_harness.domain.product.init_project import init_project

        init_project(task_dir)
        entry: dict[str, Any] = {
            "task_id": task.task_id,
            "workdir": str(task_dir),
            "prepared": True,
        }
        if not prepare_only:
            if external_score_dir is not None:
                cand = Path(external_score_dir)
                score_path = cand if cand.is_file() else cand / f"{task.task_id}.json"
                if score_path.is_file():
                    entry["scores"] = score_external(score_path)
                    entry["detail"] = "external_scored"
                else:
                    entry["scores"] = score_placeholder(task_id=task.task_id, workdir=task_dir)
                    entry["detail"] = "recorded_only_missing_external"
            else:
                entry["scores"] = score_placeholder(task_id=task.task_id, workdir=task_dir)
                entry["detail"] = "recorded_only"
            entry["ok"] = True
        results.append(entry)
    summary = {
        "suite": "wa_hard",
        "count": len(results),
        "prepare_only": prepare_only,
        "note": "scores are Manifest-only — never Gate inputs",
        "tasks": results,
    }
    summary_path = out_root / "batch_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
