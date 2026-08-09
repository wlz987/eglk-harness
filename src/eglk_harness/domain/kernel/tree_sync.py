"""Sync legacy TaskTree view from ProjectionState (transitional / SWARM compat)."""

from __future__ import annotations

from eglk_harness.domain.kernel.reducer import ProjectionState
from eglk_harness.domain.kernel.covers import covers_closure_complete
from eglk_harness.domain.kernel.tree import TaskTree, TreeNode


def tree_from_projection(state: ProjectionState) -> TaskTree | None:
    """Build TaskTree from event projection for tick/SWARM compatibility."""
    if not state.root_id or state.root_id not in state.nodes:
        return None

    def build(node_id: str) -> TreeNode:
        n = state.nodes[node_id]
        children = [build(c) for c in n.children if c in state.nodes]
        criteria: list[str] = []
        for oid in n.obligation_refs:
            ob = state.obligations.get(oid)
            if ob and ob.statement:
                criteria.append(ob.statement)
        status = n.status
        if status == "ready":
            status = "pending"
        if status == "superseded":
            status = "merged"
        return TreeNode(
            id=n.id,
            title=n.title,
            status=status,
            done_criteria=criteria or [n.title],
            children=children,
            parent_id=n.parent_id,
            split_from=n.split_from,
            merged_from=list(n.merged_from),
            repair_streak=n.repair_streak,
        )

    tree = TaskTree(root=build(state.root_id))
    tree.ensure_pointer()
    return tree


def projection_root_done(state: ProjectionState) -> bool:
    return state.run_status == "succeeded" or covers_closure_complete(state)
