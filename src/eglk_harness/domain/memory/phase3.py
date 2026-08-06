"""Phase 3: archive candidates, merge Σ, emit tick log fields."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.memory import sigma
from eglk_harness.domain.memory import skill_lib
from eglk_harness.domain.kernel.swarm import SwarmPlan


_ARCHIVE_GLOBS = (
    "explorer_*.json",
    "verifier_*.json",
    "verifier_audit_*.json",
    "pruner_*.json",
    "leaf_contract_*.json",
)
# Note: merge_suggest_*.json survives Phase-3 for next-tick apply (then deleted).


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
    distilled = skill_lib.distill_from_sigma(workdir) if merged else []
    archived = archive_candidates(loop_dir, tick=tick)

    quota = dict(quota or {})
    tokens = int(quota.get("cognitive_tokens", 0) or 0)
    tokens_max = int(quota.get("cognitive_tokens_max", 64000) or 64000)
    kind = str(decision.get("decision") or "")
    cand_count = (
        len(list((loop_dir / "candidates").glob("*.json")))
        if (loop_dir / "candidates").is_dir()
        else 0
    )
    from eglk_harness.domain.memory.context_compress import compress_tick_signals

    compressed = compress_tick_signals(
        decision=kind,
        focus_score=focus_score,
        uncertainty=uncertainty,
        cognitive_tokens=tokens,
        cognitive_tokens_max=tokens_max,
        candidate_count=cand_count,
        soft=soft,
        usd_used=float(quota.get("usd_used") or 0.0),
    )
    focus_score = float(compressed["focus_score"])
    uncertainty = float(compressed["uncertainty"])
    ns = compressed["next_swarm"]
    next_plan = SwarmPlan(
        explorer=bool(ns.get("explorer")),
        verifier=bool(ns.get("verifier")),
        pruner=bool(ns.get("pruner")),
        reasons=tuple(ns.get("reasons") or ()),
    )
    model_downgrade = compressed.get("model_downgrade") or {"active": False, "roles": {}}

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
        "skills_distilled": [d.get("id") for d in distilled],
        "candidates_archived": archived,
        "quota": dict(compressed.get("quota") or {"cognitive_tokens": tokens, "cognitive_tokens_max": tokens_max}),
        "focus_score": focus_score,
        "uncertainty": uncertainty,
        "model_downgrade": model_downgrade,
    }
    path = loop_dir / "ticks.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Mirror for status (read-only consumers); Gate does not read this file.
    state_path = loop_dir / "state.json"
    state = {
        "tick": tick,
        "quota": record["quota"],
        "focus_score": focus_score,
        "uncertainty": uncertainty,
        "last_decision": {
            "decision": decision.get("decision"),
            "reason": decision.get("reason"),
        },
        "swarm_enabled": enabled,
        "sigma_active_len": len(sigma.load_active(workdir)),
        "model_downgrade": model_downgrade,
    }
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record
