"""Threshold and constant projections (SSOT aligned with design/kernel/projections.md)."""

from __future__ import annotations

from typing import Mapping

# ── Gate abort-authoritative ──
REPAIRS_MAX: int = 8
COGNITIVE_TOKENS_MAX: int = 64000

# ── Advisor throttle (never abort) ──
CANDIDATES_MAX: int = 20  # N_max
SIGMA_STAGING_MAX: int = 50  # M_max
SIGMA_ACTIVE_MAX: int = 50
SWARM_BUDGET_FLOOR: float = 0.10

# ── Task tree ──
SPLIT_REPAIR_STREAK: int = 2
MAX_SPLIT_DEPTH: int = 4
SPLIT_CHILDREN_MIN: int = 2
SPLIT_CHILDREN_MAX: int = 4

# ── Schema identifiers (unversioned family) ──
EVENT_SCHEMA: str = "eglk.event"
GOAL_SPEC_SCHEMA: str = "eglk.goal_spec"
RUN_PROJECTION_SCHEMA: str = "eglk.run_projection"
QUOTA_SCHEMA: str = "eglk.quota"
WORK_CONTRACT_SCHEMA: str = "eglk.work_contract"
ACTION_CLAIM_SCHEMA: str = "eglk.action_claim"
EVIDENCE_BUNDLE_SCHEMA: str = "eglk.evidence_bundle"
GATE_DECISION_SCHEMA: str = "eglk.gate_decision"
TASK_STRUCTURE_SCHEMA: str = "eglk.task_structure"
WORLD_TRANSACTION_SCHEMA: str = "eglk.world_transaction"
MEMORY_RECORD_SCHEMA: str = "eglk.memory_record"
CAPABILITY_MANIFEST_SCHEMA: str = "eglk.capability_manifest"
RUN_MANIFEST_SCHEMA: str = "eglk.run_manifest"
INVARIANT_COUNT: int = 12

STATE_SCHEMA: str = RUN_PROJECTION_SCHEMA
CLAIM_SCHEMA: str = ACTION_CLAIM_SCHEMA
EVIDENCE_SCHEMA: str = EVIDENCE_BUNDLE_SCHEMA

NON_ABORT_DIAGNOSTIC: frozenset[str] = frozenset(
    {"tau_focus", "tau_unc", "focus_score", "uncertainty", "usd_used", "advisor_telemetry"}
)


def effective_cognitive_tokens_max(env: Mapping[str, str] | None = None) -> int:
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
    import os

    env = env or os.environ
    raw = (env.get("EGLK_REPAIRS_MAX") or "").strip()
    if not raw:
        return REPAIRS_MAX
    try:
        return max(0, int(raw))
    except ValueError:
        return REPAIRS_MAX


def effective_candidates_max(env: Mapping[str, str] | None = None) -> int:
    import os

    env = env or os.environ
    raw = (env.get("EGLK_CANDIDATES_MAX") or "").strip()
    if not raw:
        return CANDIDATES_MAX
    try:
        return max(1, int(raw))
    except ValueError:
        return CANDIDATES_MAX


def effective_sigma_staging_max(env: Mapping[str, str] | None = None) -> int:
    import os

    env = env or os.environ
    raw = (env.get("EGLK_SIGMA_STAGING_MAX") or "").strip()
    if not raw:
        return SIGMA_STAGING_MAX
    try:
        return max(1, int(raw))
    except ValueError:
        return SIGMA_STAGING_MAX


def as_dict() -> dict[str, object]:
    return {
        "REPAIRS_MAX": REPAIRS_MAX,
        "COGNITIVE_TOKENS_MAX": COGNITIVE_TOKENS_MAX,
        "CANDIDATES_MAX": CANDIDATES_MAX,
        "SIGMA_STAGING_MAX": SIGMA_STAGING_MAX,
        "SIGMA_ACTIVE_MAX": SIGMA_ACTIVE_MAX,
        "SWARM_BUDGET_FLOOR": SWARM_BUDGET_FLOOR,
        "SPLIT_REPAIR_STREAK": SPLIT_REPAIR_STREAK,
        "MAX_SPLIT_DEPTH": MAX_SPLIT_DEPTH,
        "SPLIT_CHILDREN_MIN": SPLIT_CHILDREN_MIN,
        "SPLIT_CHILDREN_MAX": SPLIT_CHILDREN_MAX,
        "EVENT_SCHEMA": EVENT_SCHEMA,
        "GOAL_SPEC_SCHEMA": GOAL_SPEC_SCHEMA,
        "RUN_PROJECTION_SCHEMA": RUN_PROJECTION_SCHEMA,
        "QUOTA_SCHEMA": QUOTA_SCHEMA,
        "INVARIANT_COUNT": INVARIANT_COUNT,
    }
