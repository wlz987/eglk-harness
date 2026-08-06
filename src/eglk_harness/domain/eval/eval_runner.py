"""Thin eval runner — offline scorers never feed Gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class EvalResult:
    suite: str
    task_id: str
    workdir: Path
    ok: bool
    detail: str
    scores: dict[str, Any]


def default_eval_root() -> Path | None:
    """Prefer sibling ``alw/experiment/eval`` when running from eglk-harness checkout."""
    here = Path(__file__).resolve()
    # .../alw/eglk-harness/src/eglk_harness/domain/eval/eval_runner.py → alw
    alw = here.parents[5] if len(here.parents) > 5 else None
    if alw is not None:
        cand = alw / "experiment" / "eval"
        if cand.is_dir():
            return cand
    return None


def prepare_task_workdir(
    eval_root: Path,
    *,
    suite: str,
    task_id: str,
    out_dir: Path,
) -> Path:
    """Materialize a minimal workdir for one eval task (goal + harness init files)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    goal = out_dir / ".goal.md"
    if suite == "weave_thin":
        tasks_path = eval_root / "weave_thin" / "tasks.example.json"
        task = _load_task(tasks_path, task_id)
        goal.write_text(_goal_from_task(task), encoding="utf-8")
    elif suite == "osworld_aux":
        from eglk_harness.domain.eval import osworld as osworld_mod

        tasks = {t.task_id: t for t in osworld_mod.load_pack_index(eval_root)}
        task = tasks.get(task_id)
        if task is None:
            raise KeyError(f"osworld_aux task_id not found: {task_id}")
        osworld_mod.materialize_goal(task, out_dir)
    elif suite == "scenarios":
        # Point at existing experiment run as template goal
        scenarios = eval_root / "scenarios" / "index.md"
        goal.write_text(
            f"# Scenario replay\n\nReplay task_id={task_id}\n\n"
            f"See {scenarios}\n\n## Done criteria\n\n- [ ] Scenario checklist satisfied\n",
            encoding="utf-8",
        )
    else:
        goal.write_text(
            f"# Eval {suite}/{task_id}\n\n## Done criteria\n\n"
            f"- [ ] Complete auxiliary suite task `{task_id}`\n",
            encoding="utf-8",
        )
    return out_dir


def score_offline(
    *,
    suite: str,
    task_id: str,
    workdir: Path,
    eval_root: Path,
) -> EvalResult:
    """Offline scorer — writes scores for Manifest only; never Gate input."""
    scores: dict[str, Any] = {"suite": suite, "task_id": task_id}
    if suite == "weave_thin":
        tasks_path = eval_root / "weave_thin" / "tasks.example.json"
        task = _load_task(tasks_path, task_id)
        check = task.get("check") or {}
        path = str(check.get("path") or "")
        expect = str(check.get("contains") or "")
        target = workdir / path if path else None
        ok = bool(target and target.is_file() and (not expect or expect in target.read_text(encoding="utf-8", errors="replace")))
        scores["path_exists"] = bool(target and target.is_file())
        scores["contains_ok"] = ok
        return EvalResult(suite, task_id, workdir, ok, "offline_check", scores)
    if suite == "osworld_aux":
        from eglk_harness.domain.eval import osworld as osworld_mod

        scores.update(osworld_mod.score_placeholder(task_id=task_id, workdir=workdir))
        return EvalResult(suite, task_id, workdir, True, "recorded_only", scores)
    # Placeholder suites
    return EvalResult(
        suite,
        task_id,
        workdir,
        True,
        "no_offline_scorer; recorded run only",
        scores,
    )


def _load_task(path: Path, task_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"missing tasks file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data.get("tasks") if isinstance(data, dict) else data
    if not isinstance(tasks, list):
        raise ValueError("tasks file must be a list or {tasks: [...]}")
    for t in tasks:
        if isinstance(t, dict) and str(t.get("id")) == task_id:
            return t
    raise KeyError(f"task_id not found: {task_id}")


def _goal_from_task(task: dict[str, Any]) -> str:
    title = str(task.get("title") or task.get("id") or "eval task")
    summary = str(task.get("summary") or task.get("prompt") or title)
    criteria = task.get("done_criteria") or task.get("acceptance") or []
    if not isinstance(criteria, list):
        criteria = [str(criteria)]
    if not criteria:
        criteria = [f"Satisfy: {summary}"]
    lines = [
        f"# {title}",
        "",
        "> Auxiliary eval task (Weave/OSWorld/etc). Offline scorer is NOT Gate input.",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Done criteria",
        "",
        *[f"- [ ] {c}" for c in criteria],
        "",
        "## Constraints",
        "",
        "- Do not modify `.goal.md` or `.eglk-harness/`.",
        "",
    ]
    return "\n".join(lines)
