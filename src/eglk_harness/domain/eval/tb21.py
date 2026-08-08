"""Terminal-Bench 2.1 auxiliary connector — never Gate.

Pack-first suite; optional vendor tree via ``TB21_VENDOR`` or ``EGLK_EVAL_ROOT/vendor/``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eglk_harness.domain.eval.paths import default_eval_root, vendor_dir


@dataclass
class Tb21Task:
    task_id: str
    summary: str
    notes: str = ""


def discover_vendor(eval_root: Path | None = None) -> Path | None:
    """Return optional Terminal-Bench vendor root when present."""
    roots: list[Path] = []
    env = os.environ.get("TB21_VENDOR", "").strip()
    if env:
        roots.append(Path(env))
    er = Path(eval_root).resolve() if eval_root is not None else default_eval_root()
    if er is not None:
        roots.extend(
            [
                er / "vendor" / "terminal-bench",
                er / "vendor" / "Terminal-Bench",
                er / "vendor" / "terminal-bench-2.1",
            ]
        )
    vend = vendor_dir(er)
    if vend is not None:
        roots.extend(
            [
                vend / "terminal-bench",
                vend / "Terminal-Bench",
                vend / "terminal-bench-2.1",
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
        "vendor_ready": root is not None and n >= 3,
        "file_count": n,
        "note": (
            "LH eval/ has no frozen TB tree; pack-first + optional TB21_VENDOR. "
            "Scores never feed Gate."
        ),
    }


def load_pack_index(eval_root: Path) -> list[Tb21Task]:
    """Prefer tb21/pack.json, else pack.example.json."""
    pack = Path(eval_root) / "tb21" / "pack.json"
    if not pack.is_file():
        pack = Path(eval_root) / "tb21" / "pack.example.json"
    out: list[Tb21Task] = []
    if pack.is_file():
        data = json.loads(pack.read_text(encoding="utf-8"))
        tasks = data.get("tasks") if isinstance(data, dict) else data
        if isinstance(tasks, list):
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                tid = str(t.get("id") or t.get("task_id") or "")
                if not tid:
                    continue
                out.append(
                    Tb21Task(
                        task_id=tid,
                        summary=str(
                            t.get("summary")
                            or t.get("instruction")
                            or t.get("prompt")
                            or t.get("intent")
                            or ""
                        ),
                        notes=str(t.get("notes") or ""),
                    )
                )
    return out


def materialize_goal(task: Tb21Task, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    text = (
        f"# Terminal-Bench 2.1 · {task.task_id}\n\n"
        f"> Auxiliary TB-shaped task (LH paper coverage). "
        f"Offline judge ≠ Gate input.\n\n"
        f"## Summary\n\n{task.summary or task.task_id}\n\n"
        f"## Done criteria\n\n"
        f"- [ ] Satisfy the terminal task intent for `{task.task_id}`\n"
        f"- [ ] Leave inspectable artifacts for the offline / official judge\n\n"
        f"## Notes\n\n{task.notes or 'Scores are Manifest-only — never Gate.'}\n"
    )
    goal = out_dir / ".goal.md"
    goal.write_text(text, encoding="utf-8")
    return goal


def score_from_judge_result(result_json: Path) -> dict[str, Any]:
    """Read TB-style judge JSON into Manifest-safe scores."""
    path = Path(result_json)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"judge result must be a JSON object: {path}")
    scores = data.get("scores") if isinstance(data.get("scores"), dict) else data
    out = {str(k): v for k, v in scores.items()}
    out.setdefault("judge", "tb21_external")
    out.setdefault("source", str(path))
    out["status"] = "external_scored"
    out["suite"] = "tb21"
    out.pop("admit", None)
    out.pop("gate", None)
    return out


def score_placeholder(*, task_id: str, workdir: Path, eval_root: Path | None = None) -> dict[str, Any]:
    st = vendor_status(eval_root)
    return {
        "suite": "tb21",
        "task_id": task_id,
        "judge": "tb21",
        "workdir": str(workdir),
        "status": "vendor_skipped" if not st["vendor_ready"] else "recorded_only",
        "vendor": st,
        "note": "Wire official Terminal-Bench runner externally; never feed Gate",
    }
