"""OSWorld auxiliary thin connector (辅尺；不进 Gate)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eglk_harness.domain.eval.paths import default_eval_root, vendor_dir


@dataclass
class OsWorldTask:
    task_id: str
    instruction: str
    domain: str = ""
    notes: str = ""


def load_pack_index(eval_root: Path) -> list[OsWorldTask]:
    root = Path(eval_root) / "osworld_aux"
    path = root / "pack.json"
    if not path.is_file():
        path = root / "pack.example.json"
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


def path_hint(eval_root: Path | None = None) -> Path | None:
    """Return vendor OSWorld harness path when present under the eval root."""
    er = Path(eval_root).resolve() if eval_root is not None else default_eval_root()
    cands: list[Path] = []
    if er is not None:
        cands.extend(
            [
                er / "vendor" / "LongHorizon-Harness" / "eval" / "OSWorldv2-harness",
                er / "vendor" / "OSWorldv2-harness",
            ]
        )
    vend = vendor_dir(er)
    if vend is not None:
        cands.extend(
            [
                vend / "LongHorizon-Harness" / "eval" / "OSWorldv2-harness",
                vend / "OSWorldv2-harness",
            ]
        )
    for cand in cands:
        if cand.is_dir() and any(cand.iterdir()):
            return cand
    return None


def vendor_status(eval_root: Path | None = None) -> dict[str, Any]:
    root = path_hint(eval_root)
    n = sum(1 for _ in root.rglob("*") if _.is_file()) if root else 0
    return {
        "vendor_path": str(root) if root else None,
        "vendor_ready": root is not None and n >= 5,
        "docker_ready": shutil.which("docker") is not None,
        "file_count": n,
        "note": "scores never feed Gate; skip live OSWorld when not vendor_ready",
    }


def score_external(result_json: Path) -> dict[str, Any]:
    data = json.loads(Path(result_json).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"external score must be a JSON object: {result_json}")
    scores = data.get("scores") if isinstance(data.get("scores"), dict) else data
    out = {str(k): v for k, v in scores.items()}
    out.setdefault("judge", "external_osworld")
    out.setdefault("source", str(result_json))
    out["status"] = "external_scored"
    out["suite"] = "osworld_aux"
    out.pop("admit", None)
    out.pop("gate", None)
    return out


def score_placeholder(
    *,
    task_id: str,
    workdir: Path,
    eval_root: Path | None = None,
) -> dict[str, Any]:
    st = vendor_status(eval_root)
    return {
        "suite": "osworld_aux",
        "task_id": task_id,
        "judge": "external_osworld",
        "workdir": str(workdir),
        "status": "vendor_skipped" if not st["vendor_ready"] else "recorded_only",
        "vendor": st,
        "note": "Wire OSWorldv2-harness from vendor/; never feed Gate",
        "vendor_hint": st.get("vendor_path") or "",
    }
