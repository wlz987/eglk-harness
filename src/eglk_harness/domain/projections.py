"""Threshold and constant projections (code-side pin of design/kernel/projections.md)."""

from __future__ import annotations

from typing import Mapping

# ── Gate 判定阈值 ──
TAU_DONE: float = 1.0
TAU_GAP: float = 0.5
TAU_FOCUS: float = 0.2  # SWARM throttle only — NEVER abort
TAU_UNC: float = 0.15  # legacy throttle reference — NEVER abort

REPAIRS_MAX: int = 8
COGNITIVE_TOKENS_MAX: int = 64000


def effective_cognitive_tokens_max(env: Mapping[str, str] | None = None) -> int:
    """Design default, overridable by ``EGLK_COGNITIVE_TOKENS_MAX`` / config.toml [limits]."""
    import os

    env = env or os.environ
    raw = (env.get("EGLK_COGNITIVE_TOKENS_MAX") or "").strip()
    if not raw:
        return COGNITIVE_TOKENS_MAX
    try:
        return max(1, int(raw))
    except ValueError:
        return COGNITIVE_TOKENS_MAX


def effective_repairs_max(env: Mapping[str, str] | None = None) -> int:
    """Design default, overridable by ``EGLK_REPAIRS_MAX`` / config.toml [limits]."""
    import os

    env = env or os.environ
    raw = (env.get("EGLK_REPAIRS_MAX") or "").strip()
    if not raw:
        return REPAIRS_MAX
    try:
        return max(1, int(raw))
    except ValueError:
        return REPAIRS_MAX

# ── SWARM 触发 ──
TAU_UNC_HIGH: float = 0.6
CANDIDATES_MAX: int = 20
SIGMA_ACTIVE_MAX: int = 50
SWARM_BUDGET_FLOOR: float = 0.10

# ── 任务树 ──
SPLIT_REPAIR_STREAK: int = 2
MAX_SPLIT_DEPTH: int = 4
SPLIT_CHILDREN_MIN: int = 2
SPLIT_CHILDREN_MAX: int = 4

# ── Schema pin ──
STATE_SCHEMA: str = "eglk.state/0.2.2"
GOAL_SCHEMA_VERSION: str = "0.2.2"
INVARIANT_COUNT: int = 11

# Reasons that must NEVER be treated as abort triggers by themselves
NON_ABORT_THRESHOLDS: frozenset[str] = frozenset({"tau_focus", "tau_unc", "focus_score", "uncertainty"})


def as_dict() -> dict[str, float | int | str]:
    return {
        "TAU_DONE": TAU_DONE,
        "TAU_GAP": TAU_GAP,
        "TAU_FOCUS": TAU_FOCUS,
        "TAU_UNC": TAU_UNC,
        "REPAIRS_MAX": REPAIRS_MAX,
        "COGNITIVE_TOKENS_MAX": COGNITIVE_TOKENS_MAX,
        "TAU_UNC_HIGH": TAU_UNC_HIGH,
        "CANDIDATES_MAX": CANDIDATES_MAX,
        "SIGMA_ACTIVE_MAX": SIGMA_ACTIVE_MAX,
        "SWARM_BUDGET_FLOOR": SWARM_BUDGET_FLOOR,
        "SPLIT_REPAIR_STREAK": SPLIT_REPAIR_STREAK,
        "MAX_SPLIT_DEPTH": MAX_SPLIT_DEPTH,
        "SPLIT_CHILDREN_MIN": SPLIT_CHILDREN_MIN,
        "SPLIT_CHILDREN_MAX": SPLIT_CHILDREN_MAX,
        "STATE_SCHEMA": STATE_SCHEMA,
        "GOAL_SCHEMA_VERSION": GOAL_SCHEMA_VERSION,
        "INVARIANT_COUNT": INVARIANT_COUNT,
    }
