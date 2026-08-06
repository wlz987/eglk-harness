"""Phase 3: archive candidates, merge Σ, emit tick log fields."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain import sigma
from eglk_harness.domain.swarm import SwarmPlan, decide_swarm


_ARCHIVE_GLOBS = (
    "explorer_*.json",
    "verifier_*.json",
    "verifier_audit_*.json",
    "pruner_*.json",
    "leaf_contract_*.json",
)


def archive_candidates(loop_dir: Path, *, tick: int) -> list[str]:
    """Append Phase-0/2 bypass artifacts to reasoning_log; clear them.

    Keeps ``subgoals_tree.json`` (and any non-matching files).
    """
    cand = loop_dir / "candidates"
    if not cand.is_dir():
        return []
    archived: list[str] = []
    log = loop_dir / "reasoning_log.jsonl"
    for pattern in _ARCHIVE_GLOBS:
        for path in sorted(cand.glob(pattern)):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {"raw": path.name}
            with log.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {"tick": tick, "file": path.name, "payload": data},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            archived.append(path.name)
            path.unlink(missing_ok=True)
    return archived


def run_phase3(
    workdir: Path,
    loop_dir: Path,
    *,
    tick: int,
    decision: Mapping[str, Any],
    swarm_enabled: Mapping[str, Any] | SwarmPlan | None,
    written: list[str] | None = None,
    quota: Mapping[str, Any] | None = None,
    focus_score: float = 1.0,
    uncertainty: float = 0.0,
    soft: str | None = None,
) -> dict[str, Any]:
    """Merge refined→active, archive candidates, compute next swarm plan, append ticks.jsonl."""
    merged = sigma.merge_refined_into_active(workdir, loop_dir)
    archived = archive_candidates(loop_dir, tick=tick)

    quota = dict(quota or {})
    tokens = int(quota.get("cognitive_tokens", 0) or 0)
    tokens_max = int(quota.get("cognitive_tokens_max", 64000) or 64000)
    cand_count = len(list((loop_dir / "candidates").glob("*.json"))) if (loop_dir / "candidates").is_dir() else 0
    next_plan = decide_swarm(
        focus_score=focus_score,
        uncertainty=uncertainty,
        candidate_count=cand_count,
        cognitive_tokens=tokens,
        cognitive_tokens_max=tokens_max,
        soft=soft,
    )

    if isinstance(swarm_enabled, SwarmPlan):
        enabled = swarm_enabled.to_dict()
    else:
        enabled = dict(swarm_enabled or {})

    record = {
        "tick": tick,
        "decision": decision.get("decision"),
        "reason": decision.get("reason"),
        "written": list(written or []),
        "swarm_enabled": enabled,
        "next_swarm": next_plan.to_dict(),
        "sigma_merged": merged,
        "candidates_archived": archived,
    }
    path = loop_dir / "ticks.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
