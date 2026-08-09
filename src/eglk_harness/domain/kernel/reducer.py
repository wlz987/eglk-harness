"""Deterministic Reducer: EventLog → rebuildable projections (pure)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from eglk_harness.domain.event_store import EventEnvelope
from eglk_harness.domain.kernel.projections import (
    COGNITIVE_TOKENS_MAX,
    QUOTA_SCHEMA,
    REPAIRS_MAX,
    RUN_PROJECTION_SCHEMA,
    TASK_STRUCTURE_SCHEMA,
)


@dataclass
class ObligationState:
    id: str
    requirement_id: str = ""
    parent_obligation_id: str | None = None
    statement: str = ""
    verification_type: str = "custom_attestation"
    status: str = "open"  # open | satisfied | invalidated
    origin: str = "root"
    watch_set: list[str] = field(default_factory=list)
    world_revision: int | None = None


@dataclass
class NodeState:
    id: str
    title: str
    status: str = "pending"
    obligation_refs: list[str] = field(default_factory=list)
    parent_id: str | None = None
    depth: int = 0
    children: list[str] = field(default_factory=list)
    repair_streak: int = 0
    coverage_proof_ref: str | None = None
    split_from: str | None = None
    merged_from: list[str] = field(default_factory=list)


@dataclass
class EdgeState:
    kind: str
    from_id: str
    to_id: str
    event_ref: str | None = None


@dataclass
class ProjectionState:
    goal_id: str = ""
    run_status: str = "created"
    run_status_reason: str | None = None
    last_sequence: int = -1
    last_hash: str = ""
    goal_spec_ref: str = ""
    world_revision: int = 0
    memory_digest: str = ""
    capability_manifest_ref: str | None = None
    cognitive_tokens: int = 0
    cognitive_tokens_max: int = COGNITIVE_TOKENS_MAX
    cognitive_tokens_by_role: dict[str, int] = field(default_factory=dict)
    repairs_used: int = 0
    repairs_max: int = REPAIRS_MAX
    usd_used: float = 0.0
    repair_counts: dict[str, int] = field(default_factory=dict)
    obligations: dict[str, ObligationState] = field(default_factory=dict)
    nodes: dict[str, NodeState] = field(default_factory=dict)
    root_id: str | None = None
    edges: list[EdgeState] = field(default_factory=list)
    contracts: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending_amendments: set[str] = field(default_factory=set)
    active_contract_id: str | None = None
    last_gate: dict[str, Any] | None = None


def empty_projection() -> ProjectionState:
    return ProjectionState()


def _apply(state: ProjectionState, ev: EventEnvelope) -> ProjectionState:
    s = state
    s.last_sequence = ev.sequence
    s.last_hash = ev.hash
    p = ev.payload
    t = ev.type

    if t == "RunCreated":
        s.goal_id = str(p.get("goal_id") or s.goal_id)
        s.run_status = "validating"
        s.memory_digest = str(p.get("memory_digest") or "")
        s.capability_manifest_ref = p.get("capability_manifest_ref")
        if p.get("cognitive_tokens_max") is not None:
            s.cognitive_tokens_max = int(p["cognitive_tokens_max"])
        if p.get("repairs_max") is not None:
            s.repairs_max = int(p["repairs_max"])
    elif t == "GoalCompiled":
        s.goal_spec_ref = str(p.get("goal_spec_ref") or p.get("source_digest") or "")
        s.run_status = "running"
        root_id = str(p.get("root_node_id") or "root")
        s.root_id = root_id
        if root_id not in s.nodes:
            s.nodes[root_id] = NodeState(
                id=root_id,
                title=str(p.get("title") or "root"),
                status="pending",
                obligation_refs=[str(x) for x in (p.get("obligation_refs") or [])],
                parent_id=None,
                depth=0,
            )
        for ob in p.get("obligations") or []:
            if not isinstance(ob, Mapping):
                continue
            oid = str(ob["id"])
            s.obligations[oid] = ObligationState(
                id=oid,
                requirement_id=str(ob.get("requirement_id") or ""),
                parent_obligation_id=ob.get("parent_obligation_id"),
                statement=str(ob.get("statement") or ""),
                verification_type=str(ob.get("verification_type") or "custom_attestation"),
                status=str(ob.get("status") or "open"),
                origin=str(ob.get("origin") or "root"),
            )
    elif t == "ObligationOpened":
        oid = str(p["obligation_id"])
        s.obligations[oid] = ObligationState(
            id=oid,
            requirement_id=str(p.get("requirement_id") or ""),
            parent_obligation_id=p.get("parent_obligation_id"),
            statement=str(p.get("statement") or ""),
            verification_type=str(p.get("verification_type") or "custom_attestation"),
            status="open",
            origin=str(p.get("origin") or "derived"),
        )
    elif t == "ObligationAmendmentProposed":
        s.pending_amendments.add(str(p["obligation_id"]))
    elif t == "ObligationAmended":
        oid = str(p["obligation_id"])
        s.pending_amendments.discard(oid)
        if oid in s.obligations:
            s.obligations[oid].statement = str(p.get("new_statement") or s.obligations[oid].statement)
            s.obligations[oid].status = "open"
    elif t == "ObligationAmendmentRejected":
        s.pending_amendments.discard(str(p["obligation_id"]))
    elif t == "NodeReady":
        nid = str(p["node_id"])
        if nid in s.nodes:
            s.nodes[nid].status = "ready"
    elif t == "ContractAssembled":
        cid = str(p["contract_id"])
        s.contracts[cid] = dict(p.get("contract") or p)
        s.active_contract_id = cid
        nid = str(p.get("node_id") or (p.get("contract") or {}).get("node_id") or "")
        if nid in s.nodes:
            s.nodes[nid].status = "in_progress"
            s.nodes[nid].repair_streak = s.nodes[nid].repair_streak  # keep
    elif t == "TransactionCommitted":
        s.world_revision = int(p.get("world_revision", s.world_revision + 1))
        touches = {str(x) for x in (p.get("touches") or [])}
        if touches:
            for ob in s.obligations.values():
                if ob.status == "satisfied" and set(ob.watch_set) & touches:
                    # Invalidation is emitted as separate event; reducer also mirrors
                    pass
    elif t == "ObligationSatisfied":
        oid = str(p["obligation_id"])
        if oid in s.obligations:
            s.obligations[oid].status = "satisfied"
            s.obligations[oid].watch_set = [str(x) for x in (p.get("watch_set") or [])]
            if p.get("world_revision") is not None:
                s.obligations[oid].world_revision = int(p["world_revision"])
    elif t == "ObligationInvalidated":
        oid = str(p["obligation_id"])
        if oid in s.obligations:
            s.obligations[oid].status = "invalidated"
        # Reopen owning admitted nodes
        for node in s.nodes.values():
            if oid in node.obligation_refs and node.status == "admitted":
                node.status = "in_progress"
    elif t == "GateDecided":
        s.last_gate = dict(p)
        reason = str(p.get("reason") or "")
        decision = str(p.get("decision") or "")
        nid = str(p.get("node_id") or "")
        if decision == "admit" and nid in s.nodes:
            s.nodes[nid].status = "admitted"
            s.nodes[nid].repair_streak = 0
        elif decision == "repair" and nid in s.nodes:
            s.nodes[nid].status = "ready"
            s.nodes[nid].repair_streak += 1
            s.repairs_used += 1
            s.repair_counts[reason] = int(s.repair_counts.get(reason, 0)) + 1
        elif decision == "abort" and nid in s.nodes:
            s.nodes[nid].status = "failed"
            s.repairs_used += 1
            s.repair_counts[reason] = int(s.repair_counts.get(reason, 0)) + 1
    elif t == "SplitCommitted":
        parent = str(p["node_id"])
        if parent in s.nodes:
            s.nodes[parent].status = "split"
            s.nodes[parent].coverage_proof_ref = p.get("coverage_proof_ref") or ev.event_id
        for child in p.get("children") or []:
            if not isinstance(child, Mapping):
                continue
            cid = str(child["id"])
            s.nodes[cid] = NodeState(
                id=cid,
                title=str(child.get("title") or cid),
                status="pending",
                obligation_refs=[str(x) for x in (child.get("obligation_refs") or [])],
                parent_id=parent,
                depth=int(child.get("depth") or (s.nodes[parent].depth + 1 if parent in s.nodes else 1)),
                split_from=parent,
                coverage_proof_ref=p.get("coverage_proof_ref") or ev.event_id,
            )
            if parent in s.nodes:
                s.nodes[parent].children.append(cid)
            for oid in child.get("obligation_refs") or []:
                s.edges.append(
                    EdgeState(kind="covers", from_id=cid, to_id=str(oid), event_ref=ev.event_id)
                )
    elif t == "MergeCommitted":
        into = str(p["into"])
        for nid in p.get("node_ids") or []:
            if str(nid) in s.nodes:
                s.nodes[str(nid)].status = "superseded"
        if into in s.nodes:
            s.nodes[into].obligation_refs = [str(x) for x in (p.get("obligation_refs") or s.nodes[into].obligation_refs)]
            s.nodes[into].status = "pending"
            s.nodes[into].merged_from = [str(x) for x in (p.get("node_ids") or [])]
    elif t == "QuotaUpdated":
        if p.get("cognitive_tokens") is not None:
            s.cognitive_tokens = int(p["cognitive_tokens"])
        by_role = p.get("cognitive_tokens_by_role")
        if isinstance(by_role, Mapping):
            for k, v in by_role.items():
                s.cognitive_tokens_by_role[str(k)] = int(v)
        if p.get("usd_used") is not None:
            s.usd_used = float(p["usd_used"])
        if p.get("repairs_used") is not None:
            s.repairs_used = int(p["repairs_used"])
    elif t == "RunSucceeded":
        s.run_status = "succeeded"
        s.run_status_reason = p.get("reason")
    elif t == "RunAborted":
        s.run_status = "aborted"
        s.run_status_reason = p.get("reason")
    elif t == "RunInvalid":
        s.run_status = "invalid"
        s.run_status_reason = p.get("reason")
    elif t == "RunFaulted":
        s.run_status = "faulted"
        s.run_status_reason = p.get("reason")
    elif t == "RunRecoveryStarted":
        s.run_status = "recovering"
    elif t == "RunRecoveryCompleted":
        s.run_status = str(p.get("run_status") or "running")
    return s


def reduce_events(
    events: Sequence[EventEnvelope],
    *,
    initial: ProjectionState | None = None,
) -> ProjectionState:
    state = deepcopy(initial) if initial is not None else empty_projection()
    for ev in events:
        _apply(state, ev)
    return state


def run_projection_dict(state: ProjectionState) -> dict[str, Any]:
    return {
        "schema": RUN_PROJECTION_SCHEMA,
        "goal_id": state.goal_id,
        "run_status": state.run_status,
        "run_status_reason": state.run_status_reason,
        "last_sequence": max(0, state.last_sequence),
        "last_hash": state.last_hash or ("sha256:" + "0" * 64),
        "goal_spec_ref": state.goal_spec_ref or "unset",
        "world_revision": state.world_revision,
        "quota": {
            "schema": QUOTA_SCHEMA,
            "cognitive_tokens": state.cognitive_tokens,
            "cognitive_tokens_max": state.cognitive_tokens_max,
            "cognitive_tokens_by_role": dict(state.cognitive_tokens_by_role),
            "repairs_used": state.repairs_used,
            "repairs_max": state.repairs_max,
            "usd_used": state.usd_used,
        },
        "memory_digest": state.memory_digest or ("sha256:" + "0" * 64),
        "capability_manifest_ref": state.capability_manifest_ref,
    }


def _node_tree(state: ProjectionState, node_id: str) -> dict[str, Any]:
    n = state.nodes[node_id]
    return {
        "id": n.id,
        "title": n.title,
        "status": n.status,
        "obligation_refs": list(n.obligation_refs),
        "children": [_node_tree(state, c) for c in n.children if c in state.nodes],
        "parent_id": n.parent_id,
        "depth": n.depth,
        "split_from": n.split_from,
        "merged_from": list(n.merged_from),
        "coverage_proof_ref": n.coverage_proof_ref,
    }


def task_structure_dict(state: ProjectionState) -> dict[str, Any] | None:
    if not state.root_id or state.root_id not in state.nodes:
        return None
    return {
        "schema": TASK_STRUCTURE_SCHEMA,
        "root": _node_tree(state, state.root_id),
        "edges": [
            {
                "kind": e.kind,
                "from": e.from_id,
                "to": e.to_id,
                "event_ref": e.event_ref,
            }
            for e in state.edges
        ],
    }
