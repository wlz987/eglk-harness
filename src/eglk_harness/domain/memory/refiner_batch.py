"""Run-end Refiner batch — design: multi_agent §5.4 (not per-tick)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.adapters.base import AgentAdapter
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.event_runtime import RunEventContext
from eglk_harness.domain.memory import sigma
from eglk_harness.domain.memory.memory_promotion import run_cross_run_promotion_async
from eglk_harness.domain.runtime.budgets import timeout_for_role
from eglk_harness.domain.runtime.bypass_llm import coerce_refiner, run_bypass_json

_TERMINAL = frozenset({"succeeded", "aborted", "invalid", "faulted"})


def _gap_bits(evidence: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(evidence, Mapping):
        return []
    gaps = evidence.get("gaps") or evidence.get("verdicts")
    if not isinstance(gaps, list):
        return []
    texts: list[str] = []
    for g in gaps[:6]:
        if isinstance(g, dict):
            texts.append(str(g.get("text") or g.get("title") or g.get("obligation_id") or g))
        else:
            texts.append(str(g))
    return texts


def mechanical_lesson(
    *,
    tick: int,
    decision: str,
    reason: str = "",
    leaf: str = "",
    claim: Mapping[str, Any] | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stage-only lesson snapshot (no LLM); polished at run end."""
    kind = str(decision or "")
    gaps = _gap_bits(evidence)
    if kind == "abort":
        return {
            "id": f"sigma-abort-{tick:03d}",
            "kind": "archive",
            "decision": kind,
            "reason": reason,
            "leaf_id": leaf,
            "conf": 0.5,
            "staged": "mechanical",
        }
    if kind == "repair":
        text = f"repair:{reason}"
        if gaps:
            text = f"{text}; gaps: {'; '.join(gaps[:2])}"
        return {
            "id": f"sigma-lesson-{tick:03d}",
            "kind": "lesson",
            "cond": reason,
            "text": text,
            "leaf_id": leaf,
            "gaps": gaps,
            "conf": 0.6,
            "staged": "mechanical",
        }
    return {
        "id": f"sigma-hit-{tick:03d}",
        "kind": "hit",
        "text": "admit reinforced",
        "leaf_id": leaf,
        "conf": 0.7,
        "staged": "mechanical",
    }


def stage_tick_lesson(
    loop_dir: Path,
    *,
    tick: int,
    decision: Mapping[str, Any] | None,
    claim: Mapping[str, Any] | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> Path | None:
    """Mechanically stage one tick lesson under ``sigma/refined/`` (no LLM)."""
    if not isinstance(decision, Mapping):
        return None
    kind = str(decision.get("decision") or "")
    if kind not in {"repair", "admit", "abort"}:
        return None
    target = sigma.refined_dir(loop_dir) / f"{tick:03d}.json"
    if target.is_file():
        return target
    sigma.enforce_staging_cap(loop_dir)
    item = mechanical_lesson(
        tick=tick,
        decision=kind,
        reason=str(decision.get("reason") or ""),
        leaf=str(decision.get("subgoal_id") or "root"),
        claim=claim,
        evidence=evidence,
    )
    path = sigma.write_refined(loop_dir, tick, item)
    sigma.enforce_staging_cap(loop_dir)
    return path


def stage_lessons_from_ticks(loop_dir: Path) -> int:
    """Backfill mechanical staging from ``ticks.jsonl`` when missing per-tick files."""
    path = loop_dir / "ticks.jsonl"
    if not path.is_file():
        return 0
    staged = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        tick = rec.get("tick")
        if tick is None:
            continue
        try:
            tick_i = int(tick)
        except (TypeError, ValueError):
            continue
        decision = {
            "decision": rec.get("decision"),
            "reason": rec.get("reason"),
            "subgoal_id": "root",
        }
        if stage_tick_lesson(loop_dir, tick=tick_i, decision=decision):
            staged += 1
    return staged


async def polish_refined_staging(
    adapter: AgentAdapter,
    workdir: Path,
    loop_dir: Path,
    *,
    goal_id: str,
) -> dict[str, Any]:
    """Run-end Refiner LLM polish on staged ``sigma/refined/*.json`` only."""
    paths_list = sigma.list_refined(loop_dir)
    sigma.enforce_staging_cap(loop_dir)
    paths_list = sigma.list_refined(loop_dir)
    if not paths_list:
        return {"count": 0, "tokens": 0, "cost_usd": 0.0}
    tokens = 0
    cost = 0.0
    count = 0
    for path in paths_list:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        tick = int(path.stem) if path.stem.isdigit() else 0
        fallback = dict(raw)
        leaf_block = (
            f"[REFINE batch goal={goal_id}]\n"
            f"tick={tick}\n"
            f"staged={json.dumps(raw, ensure_ascii=False)[:1200]}"
        )
        result = await run_bypass_json(
            adapter,
            role="refiner",
            workdir=workdir,
            leaf_block=leaf_block,
            extra='JSON: {"id","kind","text","conf"}',
            tick=tick,
            subgoal_id=str(raw.get("leaf_id") or "root"),
            timeout_s=float(timeout_for_role("refiner")),
            force=True,
        )
        if result is None:
            item = fallback
        else:
            item = coerce_refiner(result, fallback=fallback)
            tokens += int(result.get("tokens") or 0)
            cost += float(result.get("cost_usd") or 0.0)
        path.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        count += 1
    return {"count": count, "tokens": tokens, "cost_usd": cost}


async def run_end_refiner_batch(
    workdir: Path,
    goal_id: str,
    adapter: AgentAdapter,
) -> dict[str, Any]:
    """Terminal-only Refiner: stage → polish → flush to Σ ``candidate`` (never ``active``)."""
    ctx = RunEventContext(workdir, goal_id)
    ctx.acquire()
    try:
        proj = ctx.handler.projection()
        run_status = str(proj.run_status or "")
        if run_status not in _TERMINAL:
            return {"ok": True, "skipped": True, "reason": "not_terminal", "run_status": run_status}

        loop_dir = ctx.loop_dir
        origin_run_id = f"run-{goal_id}-seq{proj.last_sequence}"
        cross_run = await run_cross_run_promotion_async(
            workdir,
            adapter,
            goal_id=goal_id,
            origin_run_id=origin_run_id,
            handler=ctx.handler,
            workdir_namespace=goal_id,
        )
        if int(cross_run.get("tokens") or 0) > 0:
            ctx.quota(
                "refiner",
                max(1, int(cross_run.get("tokens") or 0)),
                float(cross_run.get("cost_usd") or 0.0),
            )
        stage_lessons_from_ticks(loop_dir)
        polished = await polish_refined_staging(adapter, workdir, loop_dir, goal_id=goal_id)
        if int(polished.get("count") or 0) > 0:
            ctx.quota(
                "refiner",
                max(1, int(polished.get("tokens") or 0)),
                float(polished.get("cost_usd") or 0.0),
            )

        flushed = sigma.flush_refined_to_candidates(
            workdir,
            loop_dir,
            goal_id=goal_id,
            origin_run_id=origin_run_id,
            handler=ctx.handler,
        )
        ctx.export_projections()
        return {
            "ok": True,
            "run_status": run_status,
            "cross_run_promotion": cross_run,
            "polished": polished,
            "flushed_to_candidate": flushed,
        }
    finally:
        ctx.release()
