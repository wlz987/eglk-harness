"""Covers-graph helpers — parent obligation promotion & closure checks."""

from __future__ import annotations

from typing import Any

from eglk_harness.domain.kernel.reducer import ProjectionState


def derived_children(state: ProjectionState, parent_id: str) -> list[str]:
    """Obligation ids whose ``parent_obligation_id`` equals ``parent_id``."""
    return [
        oid
        for oid, ob in state.obligations.items()
        if ob.parent_obligation_id is not None and str(ob.parent_obligation_id) == parent_id
    ]


def parents_ready_to_promote(state: ProjectionState) -> list[str]:
    """Parents whose every derived child obligation is ``satisfied``."""
    ready: list[str] = []
    seen_parents: set[str] = set()
    for ob in state.obligations.values():
        if ob.parent_obligation_id is None:
            continue
        pid = str(ob.parent_obligation_id)
        if pid in seen_parents:
            continue
        seen_parents.add(pid)
        parent = state.obligations.get(pid)
        if parent is None or parent.status == "satisfied":
            continue
        kids = derived_children(state, pid)
        if not kids:
            continue
        if all(state.obligations[k].status == "satisfied" for k in kids):
            ready.append(pid)
    return ready


def obligation_covered(state: ProjectionState, oid: str, *, _stack: frozenset[str] | None = None) -> bool:
    """True if obligation is satisfied, or all derived covers are recursively covered."""
    stack = _stack or frozenset()
    if oid in stack:
        return False
    ob = state.obligations.get(oid)
    if ob is None:
        return False
    if ob.status == "satisfied":
        return True
    kids = derived_children(state, oid)
    if not kids:
        return False
    nxt = stack | {oid}
    return all(obligation_covered(state, k, _stack=nxt) for k in kids)


def covers_closure_complete(state: ProjectionState) -> bool:
    """Root closure: every root-origin obligation is covered under current revision."""
    if not state.root_id or state.root_id not in state.nodes:
        return False
    root = state.nodes[state.root_id]
    refs = list(root.obligation_refs)
    if not refs:
        refs = [oid for oid, ob in state.obligations.items() if ob.origin == "root"]
    if not refs:
        return False
    return all(obligation_covered(state, oid) for oid in refs)


def node_obligations_closed(state: ProjectionState, node_id: str) -> bool:
    """Leaf/internal node admits when each of its obligation_refs is covered."""
    node = state.nodes.get(node_id)
    if node is None:
        return False
    refs = list(node.obligation_refs)
    if not refs:
        return True
    return all(obligation_covered(state, oid) for oid in refs)


def covers_edges_from_refinement(
    opened: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build obligation→obligation covers edges for SplitCommitted payload."""
    edges: list[dict[str, str]] = []
    for ob in opened:
        oid = str(ob.get("id") or "")
        parent = ob.get("parent_obligation_id")
        if oid and parent is not None:
            edges.append({"kind": "covers", "from": oid, "to": str(parent)})
    return edges
