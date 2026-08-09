"""Async Refiner review of quarantined Σ records (LLM value judgment)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.adapters.base import AgentAdapter
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.memory.lifecycle import bump_verification, deprecate_record
from eglk_harness.domain.memory.memory_promotion import _mark_reviewed, is_sensitive
from eglk_harness.domain.runtime.budgets import timeout_for_role
from eglk_harness.domain.runtime.bypass_llm import bypass_llm_enabled, run_bypass_json


def _mechanical_worth_review(data: Mapping[str, Any]) -> bool:
    return float(data.get("conf") or 0) >= 0.5


def _parse_review(doc: Mapping[str, Any] | None, *, fallback: Mapping[str, Any]) -> tuple[bool, float]:
    if not isinstance(doc, Mapping):
        return _mechanical_worth_review(fallback), float(fallback.get("conf") or 0)
    worth = doc.get("worth_review")
    if worth is None:
        worth = doc.get("keep")
    if isinstance(worth, bool):
        conf = float(doc.get("conf") or fallback.get("conf") or 0)
        return worth, conf
    return _mechanical_worth_review(fallback), float(fallback.get("conf") or 0)


async def llm_review_quarantined(
    adapter: AgentAdapter | None,
    workdir: Path,
    *,
    goal_id: str,
    origin_run_id: str,
    handler: Any | None = None,
) -> dict[str, Any]:
    """Refiner judges quarantined records; bump or deprecate (not blind bump)."""
    dirs = paths.memory_lifecycle_dirs(workdir)
    quarantined = dirs["quarantined"]
    if not quarantined.is_dir():
        return {"reviewed": 0, "verification_bumps": 0, "deprecated": 0, "tokens": 0, "cost_usd": 0.0}

    reviewed = 0
    bumped = 0
    deprecated = 0
    tokens = 0
    cost = 0.0
    use_llm = adapter is not None and bypass_llm_enabled(adapter)

    for p in sorted(quarantined.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or is_sensitive(data):
            continue
        prov = data.get("provenance") if isinstance(data.get("provenance"), Mapping) else {}
        origin_run = str(prov.get("origin_run_id") or "")
        if origin_run and origin_run == origin_run_id:
            continue
        rid = str(data.get("id") or p.stem)
        worth = _mechanical_worth_review(data)
        conf = float(data.get("conf") or 0)
        if use_llm:
            leaf_block = (
                f"[REFINER quarantine review goal={goal_id}]\n"
                f"record={json.dumps(data, ensure_ascii=False)[:1500]}"
            )
            raw = await run_bypass_json(
                adapter,
                role="refiner",
                workdir=workdir,
                leaf_block=leaf_block,
                extra='JSON: {"worth_review":bool,"conf":float,"reason":""}',
                tick=0,
                subgoal_id=goal_id,
                timeout_s=float(timeout_for_role("refiner")),
                force=True,
            )
            if raw is not None:
                tokens += int(raw.get("tokens") or 0)
                cost += float(raw.get("cost_usd") or 0.0)
            worth, conf = _parse_review(raw, fallback=data)
            if conf > float(data.get("conf") or 0):
                data["conf"] = conf
                p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        reviewed += 1
        if not worth:
            if deprecate_record(workdir, rid, reason="refiner_reject", handler=handler):
                deprecated += 1
            continue
        _mark_reviewed(workdir, p, goal_id)
        if bump_verification(workdir, rid) is not None:
            bumped += 1

    return {
        "reviewed": reviewed,
        "verification_bumps": bumped,
        "deprecated": deprecated,
        "tokens": tokens,
        "cost_usd": cost,
        "llm": use_llm,
    }
