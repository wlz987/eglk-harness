"""Thin eval runner — offline scorers never feed Gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eglk_harness.domain.eval.loader import load_suite_module
from eglk_harness.domain.eval.suite_ops import (
    _PACK_SUITES,
    materialize_task,
    resolve_pack_task,
    score_task,
)


@dataclass
class EvalResult:
    suite: str
    task_id: str
    workdir: Path
    ok: bool
    detail: str
    scores: dict[str, Any]


def prepare_task_workdir(
    eval_root: Path,
    *,
    suite: str,
    task_id: str,
    out_dir: Path,
) -> Path:
    """Materialize a minimal workdir for one eval task (goal + harness init files)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if suite in _PACK_SUITES:
        mod = load_suite_module(suite, eval_root)
        task = resolve_pack_task(mod, eval_root, task_id)
        if task is None:
            raise KeyError(f"{suite} task_id not found: {task_id}")
        materialize_task(mod, task, out_dir)
        return out_dir

    goal = out_dir / ".goal.md"
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
    if suite in _PACK_SUITES:
        mod = load_suite_module(suite, eval_root)
        scores, ok, detail = score_task(
            mod,
            suite=suite,
            task_id=task_id,
            workdir=workdir,
            eval_root=eval_root,
        )
        return EvalResult(suite, task_id, workdir, ok, detail, scores)

    scores: dict[str, Any] = {"suite": suite, "task_id": task_id}
    return EvalResult(
        suite,
        task_id,
        workdir,
        True,
        "no_offline_scorer; recorded run only",
        scores,
    )
