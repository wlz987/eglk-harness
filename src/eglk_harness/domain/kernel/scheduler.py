"""Deterministic Scheduler — select next ready leaf and assemble WorkContract."""

from __future__ import annotations

import uuid
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel.projections import (
    CANDIDATES_MAX,
    SWARM_BUDGET_FLOOR,
    WORK_CONTRACT_SCHEMA,
)
from eglk_harness.domain.kernel.reducer import ProjectionState


def pending_ready_to_promote(state: ProjectionState) -> list[str]:
    """Pending nodes whose ``depends_on`` prerequisites are admitted (deterministic order)."""
    out: list[str] = []
    for nid, node in state.nodes.items():
        if node.status != "pending":
            continue
        if any(oid in state.pending_amendments for oid in node.obligation_refs):
            continue
        if not deps_satisfied(state, nid):
            continue
        out.append(nid)
    return sorted(out)


def deps_satisfied(state: ProjectionState, node_id: str) -> bool:
    """``depends_on`` edges: from=dependent, to=prerequisite must be admitted."""
    for e in state.edges:
        if e.kind != "depends_on":
            continue
        if e.from_id != node_id:
            continue
        pre = state.nodes.get(e.to_id)
        if pre is None or pre.status != "admitted":
            return False
    return True


def ready_pool(state: ProjectionState) -> list[str]:
    """Nodes with status=ready, deps met, and no pending amendments."""
    out: list[str] = []
    for nid, node in state.nodes.items():
        if node.status != "ready":
            continue
        if any(oid in state.pending_amendments for oid in node.obligation_refs):
            continue
        if not deps_satisfied(state, nid):
            continue
        out.append(nid)
    return out


def select_ready_node(state: ProjectionState) -> str | None:
    """Depth-desc, then node_id lexicographic — fully deterministic."""
    pool = ready_pool(state)
    if not pool:
        return None

    def key(nid: str) -> tuple[int, str]:
        n = state.nodes[nid]
        return (-n.depth, nid)

    return sorted(pool, key=key)[0]


def assemble_work_contract(
    state: ProjectionState,
    node_id: str,
    *,
    capabilities: Sequence[str] | None = None,
    side_effect_class_ceiling: Sequence[str] | None = None,
    cognitive_tokens_soft: int = 4000,
    prior_evidence_refs: Sequence[str] | None = None,
    allowed_scope: Sequence[str] | None = None,
    forbidden_actions: Sequence[str] | None = None,
    dependencies: Sequence[str] | None = None,
    repair_feedback: Mapping[str, Any] | None = None,
    obligation_verification_types: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    node = state.nodes[node_id]
    deps: list[str] = []
    for e in state.edges:
        if e.kind == "depends_on" and e.from_id == node_id:
            pre = state.nodes.get(e.to_id)
            if pre is not None and pre.status == "admitted":
                deps.append(e.to_id)
    # Prefer explicit type map; else derive from ledger for this node's refs
    type_map: dict[str, str] = dict(obligation_verification_types or {})
    if not type_map:
        for oid in node.obligation_refs:
            ob = state.obligations.get(oid)
            if ob is not None:
                type_map[oid] = str(ob.verification_type or "custom_attestation")
    out: dict[str, Any] = {
        "schema": WORK_CONTRACT_SCHEMA,
        "contract_id": f"wc-{uuid.uuid4().hex[:12]}",
        "node_id": node_id,
        "world_revision_base": state.world_revision,
        "obligation_refs": list(node.obligation_refs) or ["__none__"],
        "dependencies": list(dependencies if dependencies is not None else deps),
        "boundary": {
            "allowed_scope": list(allowed_scope or ["workdir/**", "repo/**"]),
            "forbidden_actions": list(forbidden_actions or []),
        },
        "capabilities": list(capabilities or []),
        "transaction_policy": {
            "side_effect_class_ceiling": list(
                side_effect_class_ceiling or ["read_only", "reversible"]
            )
        },
        "budget": {"cognitive_tokens_soft": int(cognitive_tokens_soft)},
        "prior_evidence_refs": list(prior_evidence_refs or []),
    }
    if type_map:
        out["obligation_verification_types"] = type_map
    if isinstance(repair_feedback, Mapping) and repair_feedback.get("prior_decision") == "repair":
        out["repair_feedback"] = dict(repair_feedback)
    return out


def advisor_plan(
    state: ProjectionState,
    *,
    candidates_count: int = 0,
    swarm_soft: str | None = None,
) -> dict[str, bool]:
    """Event-trigger advisor enablement (never abort).

    ``swarm_soft='0'`` forces Explorer/Verifier off (eval soft switch).
    """
    tokens = state.cognitive_tokens
    tokens_max = max(1, state.cognitive_tokens_max)
    remaining_ratio = max(0.0, 1.0 - (tokens / tokens_max))
    budget_tight = remaining_ratio < SWARM_BUDGET_FLOOR
    force_selector = candidates_count > CANDIDATES_MAX
    explorer = True
    verifier = force_selector
    if swarm_soft == "0" or budget_tight:
        explorer = False
        verifier = False
    return {
        "governor": True,  # structural; still event-triggered by repair streak
        "explorer": explorer,
        "verifier": verifier,
        "candidate_selector": force_selector,
        "refiner": False,  # run-end only
    }


def should_propose_split(state: ProjectionState, node_id: str, streak_threshold: int) -> bool:
    node = state.nodes.get(node_id)
    if node is None:
        return False
    if node.depth >= __import__(
        "eglk_harness.domain.kernel.projections", fromlist=["MAX_SPLIT_DEPTH"]
    ).MAX_SPLIT_DEPTH:
        return False
    return node.repair_streak >= streak_threshold


def pick_sibling_merge_pair(
    state: ProjectionState, *, min_criteria_sim: float = 0.5
) -> tuple[str, list[str], float] | None:
    """Return ``(parent_id, node_ids, score)`` for the best overlapping sibling pair."""
    from eglk_harness.domain.memory.sigma_merge import text_similarity
    from eglk_harness.domain.kernel.projection_view import iter_sibling_leaf_groups

    best_score = 0.0
    best: tuple[str, list[str], float] | None = None
    for parent_id, leaves in iter_sibling_leaf_groups(state):
        ready = [w for w in leaves if w.status == "ready"]
        if len(ready) < 2:
            continue
        for i, a in enumerate(ready):
            for b in ready[i + 1 :]:
                sim = text_similarity(" ".join(a.done_criteria), " ".join(b.done_criteria))
                if sim >= min_criteria_sim and sim > best_score:
                    best_score = sim
                    best = (parent_id, [a.id, b.id], sim)
    return best


def should_propose_merge(state: ProjectionState, *, min_criteria_sim: float = 0.5) -> bool:
    """True when sibling ``ready`` leaves share overlapping acceptance (Governor merge)."""
    return pick_sibling_merge_pair(state, min_criteria_sim=min_criteria_sim) is not None


def coverage_complete(state: ProjectionState) -> bool:
    """Root closure: all root obligations satisfied and no open/invalidated remain uncovered."""
    if not state.root_id or state.root_id not in state.nodes:
        return False
    root = state.nodes[state.root_id]
    refs = list(root.obligation_refs)
    if not refs:
        # derive from all root-origin obligations
        refs = [oid for oid, ob in state.obligations.items() if ob.origin == "root"]
    if not refs:
        return False
    for oid in refs:
        ob = state.obligations.get(oid)
        if ob is None or ob.status != "satisfied":
            return False
    return True
