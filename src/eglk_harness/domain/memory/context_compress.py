"""Phase-3 context-compress helpers (Phase-3 compress helpers)."""

from __future__ import annotations

from typing import Any

from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.swarm import SwarmPlan, decide_swarm
from eglk_harness.domain.memory.tokens import update_focus_uncertainty


def compress_tick_signals(
    *,
    decision: str,
    focus_score: float,
    uncertainty: float,
    cognitive_tokens: int,
    cognitive_tokens_max: int = P.COGNITIVE_TOKENS_MAX,
    candidate_count: int = 0,
    soft: str | None = None,
    usd_used: float = 0.0,
) -> dict[str, Any]:
    """Update focus/uncertainty and compute next swarm plan (never abort on τ)."""
    from eglk_harness.domain.runtime.models import plan_model_downgrade, set_active_downgrade

    focus, unc = update_focus_uncertainty(
        decision=decision, focus_score=focus_score, uncertainty=uncertainty
    )
    plan = decide_swarm(
        focus_score=focus,
        uncertainty=unc,
        candidate_count=candidate_count,
        cognitive_tokens=cognitive_tokens,
        cognitive_tokens_max=cognitive_tokens_max,
        soft=soft,
    )
    downgrade = plan_model_downgrade(usd_used=float(usd_used or 0.0))
    set_active_downgrade(downgrade.get("roles") if downgrade.get("active") else {})
    return {
        "focus_score": focus,
        "uncertainty": unc,
        "next_swarm": plan.to_dict() if isinstance(plan, SwarmPlan) else plan,
        "quota": {
            "cognitive_tokens": cognitive_tokens,
            "cognitive_tokens_max": cognitive_tokens_max,
            "usd_used": float(usd_used or 0.0),
        },
        "model_downgrade": downgrade,
    }
