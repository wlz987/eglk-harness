"""Generic eval suite CLI helpers — connectors live in ``EGLK_EVAL_ROOT/lib/``."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import ModuleType
from typing import Any

_PACK_SUITES = frozenset(
    {"wa_hard", "osworld_aux", "weave_lh", "tb21", "weave_thin", "scenarios"}
)


def task_summary(task: Any) -> str:
    for attr in ("intent", "summary", "instruction"):
        val = getattr(task, attr, None)
        if val:
            return str(val)
    return str(getattr(task, "task_id", ""))


def list_task_rows(mod: ModuleType, eval_root: Path) -> list[dict[str, str]]:
    return [
        {"id": str(t.task_id), "summary": task_summary(t)}
        for t in mod.load_pack_index(eval_root)
    ]


def load_task_index(mod: ModuleType, eval_root: Path) -> dict[str, Any]:
    return {t.task_id: t for t in mod.load_pack_index(eval_root)}


def _synthetic_task(mod: ModuleType, task_id: str) -> Any | None:
    for cls_name in ("WaHardTask", "OsWorldTask", "WeaveLhTask", "Tb21Task"):
        cls = getattr(mod, cls_name, None)
        if cls is None:
            continue
        kwargs: dict[str, Any] = {"task_id": str(task_id)}
        fields = getattr(cls, "__dataclass_fields__", {})
        for name in fields:
            if name == "task_id":
                continue
            if name in ("intent", "summary", "instruction"):
                kwargs[name] = f"External score for {task_id}"
            elif name == "sites":
                kwargs[name] = []
            elif name in ("notes", "domain"):
                kwargs[name] = ""
        try:
            return cls(**kwargs)
        except TypeError:
            continue
    return None


def resolve_pack_task(
    mod: ModuleType,
    eval_root: Path,
    task_id: str,
    *,
    allow_synthetic: bool = False,
) -> Any | None:
    task = load_task_index(mod, eval_root).get(task_id)
    if task is not None:
        return task
    if allow_synthetic:
        return _synthetic_task(mod, task_id)
    return None


def materialize_task(mod: ModuleType, task: Any, out_dir: Path) -> None:
    mod.materialize_goal(task, out_dir)


def _eval_result_path(runs: Path, task_id: str) -> Path | None:
    cand = runs / str(task_id) / "eval_result.json"
    if cand.is_file():
        return cand
    root = runs / "eval_result.json"
    if root.is_file():
        return root
    return None


def _placeholder_kwargs(mod: ModuleType, eval_root: Path, task_id: str, workdir: Path) -> dict[str, Any]:
    fn = mod.score_placeholder
    kwargs: dict[str, Any] = {"task_id": task_id, "workdir": workdir}
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    if "eval_root" in params:
        kwargs["eval_root"] = eval_root
    return kwargs


def score_task(
    mod: ModuleType,
    *,
    suite: str,
    task_id: str,
    workdir: Path,
    eval_root: Path,
    external_score: Path | None = None,
    score_har: Path | None = None,
    score_agent_runs: Path | None = None,
) -> tuple[dict[str, Any], bool, str]:
    """Offline scorer dispatch — Manifest-only; never Gate."""
    if score_agent_runs is not None and hasattr(mod, "score_from_eval_result"):
        cand = _eval_result_path(score_agent_runs, task_id)
        if cand is not None:
            scores = dict(mod.score_from_eval_result(cand))
            ok = bool(float(scores.get("success") or 0) >= 1.0)
            return scores, ok, "official_scored"
        if hasattr(mod, "score_placeholder"):
            scores = dict(mod.score_placeholder(**_placeholder_kwargs(mod, eval_root, task_id, workdir)))
            return scores, False, "missing_eval_result"

    if score_har is not None and hasattr(mod, "score_har_offline"):
        scores = dict(mod.score_har_offline(score_har))
        ok = bool(float(scores.get("success") or 0) >= 1.0)
        return scores, ok, "har_offline_scored"

    if external_score is not None:
        for fn_name in ("score_external", "score_from_judge_result"):
            fn = getattr(mod, fn_name, None)
            if fn is None:
                continue
            scores = dict(fn(external_score))
            ok = bool(float(scores.get("success") or scores.get("pass") or 0) >= 1.0)
            if scores.get("status") == "external_scored":
                ok = True
            return scores, ok, f"{suite}_external"

    if hasattr(mod, "score_placeholder"):
        scores = dict(mod.score_placeholder(**_placeholder_kwargs(mod, eval_root, task_id, workdir)))
        if hasattr(mod, "path_hint"):
            hint = mod.path_hint(eval_root)
            if hint is not None:
                scores["vendor_hint"] = str(hint)
        detail = str(scores.get("status") or "recorded_only")
        return scores, True, detail

    return {"suite": suite, "task_id": task_id}, True, "no_offline_scorer; recorded run only"


def run_batch(
    mod: ModuleType,
    eval_root: Path,
    out_root: Path,
    *,
    limit: int | None,
    prepare_only: bool,
    external_score_dir: Path | None,
) -> dict[str, Any]:
    if not hasattr(mod, "run_batch"):
        raise NotImplementedError("suite module has no run_batch()")
    return mod.run_batch(
        eval_root,
        out_root=out_root,
        limit=limit,
        prepare_only=prepare_only,
        external_score_dir=external_score_dir,
    )


def merge_agent_run_scores(summary: dict[str, Any], ingested: dict[str, Any]) -> dict[str, Any]:
    by_id = {r["task_id"]: r for r in ingested.get("tasks") or []}
    for entry in summary.get("tasks") or []:
        row = by_id.get(str(entry.get("task_id")))
        if row:
            entry["scores"] = row.get("scores")
            entry["detail"] = row.get("detail")
            entry["ok"] = bool(row.get("ok"))
    summary["agent_runs"] = ingested
    summary["note"] = "official agent-run scores — Manifest-only; never Gate"
    return summary
