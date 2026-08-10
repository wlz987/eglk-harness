"""ProjectionState work-node view — SSOT for tick orchestration (no legacy TaskTree)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel.reducer import ProjectionState
from eglk_harness.domain.kernel.covers import covers_closure_complete


@dataclass(frozen=True)
class WorkNode:
    """Leaf-shaped view derived from event projection."""

    id: str
    title: str
    done_criteria: list[str]
    repair_streak: int = 0
    parent_id: str | None = None
    status: str = "pending"


def node_criteria(state: ProjectionState, node_id: str) -> list[str]:
    node = state.nodes.get(node_id)
    if node is None:
        return []
    out: list[str] = []
    for oid in node.obligation_refs:
        ob = state.obligations.get(oid)
        if ob and ob.statement:
            out.append(ob.statement)
    if out:
        return out
    if node.title:
        return [node.title]
    return []


def work_node(state: ProjectionState, node_id: str) -> WorkNode | None:
    node = state.nodes.get(node_id)
    if node is None:
        return None
    return WorkNode(
        id=node.id,
        title=node.title,
        done_criteria=node_criteria(state, node_id),
        repair_streak=int(node.repair_streak),
        parent_id=node.parent_id,
        status=node.status,
    )


def in_progress_node(state: ProjectionState) -> WorkNode | None:
    for nid, node in state.nodes.items():
        if node.status == "in_progress":
            return work_node(state, nid)
    return None


def active_work_node(state: ProjectionState, selected_id: str | None = None) -> WorkNode | None:
    """In-progress leaf, else explicit id."""
    cur = in_progress_node(state)
    if cur is not None:
        return cur
    if selected_id:
        return work_node(state, selected_id)
    return None


def root_done_criteria(state: ProjectionState) -> list[str]:
    root_id = state.root_id or "root"
    return node_criteria(state, root_id)


MERGEABLE_LEAF_STATUSES = frozenset({"ready", "in_progress", "admitted"})


def projection_root_done(state: ProjectionState) -> bool:
    return state.run_status == "succeeded" or covers_closure_complete(state)


def iter_sibling_leaf_groups(state: ProjectionState) -> list[tuple[str, list[WorkNode]]]:
    """Parents with two or more mergeable leaf children (ready / in_progress / admitted)."""
    groups: list[tuple[str, list[WorkNode]]] = []
    for parent_id, parent in state.nodes.items():
        if not parent.children:
            continue
        leaves: list[WorkNode] = []
        for cid in parent.children:
            if cid not in state.nodes:
                continue
            child = state.nodes[cid]
            if child.children:
                continue
            if child.status not in MERGEABLE_LEAF_STATUSES:
                continue
            wn = work_node(state, cid)
            if wn is not None:
                leaves.append(wn)
        if len(leaves) >= 2:
            groups.append((parent_id, leaves))
    return groups


def split_depends_on_chain(child_ids: Sequence[str]) -> list[dict[str, str]]:
    """Sequential depends_on: child[i] depends on child[i-1] (must be admitted first)."""
    ids = [str(x) for x in child_ids if str(x)]
    edges: list[dict[str, str]] = []
    for i in range(1, len(ids)):
        edges.append({"from": ids[i], "to": ids[i - 1], "kind": "depends_on"})
    return edges


def all_work_admitted(state: ProjectionState) -> bool:
    """True when every schedulable leaf is admitted or structurally terminal."""
    terminal = {"admitted", "failed", "split", "superseded", "merged"}
    for node in state.nodes.values():
        if node.children:
            continue
        if node.status in terminal:
            continue
        return False
    return True


def _find_node_dict(root: Mapping[str, Any], node_id: str) -> dict[str, Any] | None:
    if str(root.get("id")) == node_id:
        return dict(root)
    for ch in root.get("children") or []:
        if isinstance(ch, Mapping):
            found = _find_node_dict(ch, node_id)
            if found is not None:
                return found
    return None


def work_node_from_task_structure(loop_dir: Path, node_id: str) -> WorkNode | None:
    """Read exported ``task_structure.json`` + ``obligation_ledger.json`` (projection mirror)."""
    from eglk_harness.domain.kernel.loop_store import read_json

    base = Path(loop_dir) / "projections"
    ts_path = base / "task_structure.json"
    ol_path = base / "obligation_ledger.json"
    if not ts_path.is_file():
        return None
    try:
        ts = read_json(ts_path)
        ol = read_json(ol_path) if ol_path.is_file() else {}
    except (OSError, ValueError, TypeError):
        return None
    root = ts.get("root") if isinstance(ts, dict) else None
    if not isinstance(root, Mapping):
        return None
    nd = _find_node_dict(root, node_id)
    if nd is None:
        return None
    ob_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(ol, dict):
        for ob in ol.get("obligations") or []:
            if isinstance(ob, dict) and ob.get("id"):
                ob_by_id[str(ob["id"])] = ob
    criteria: list[str] = []
    for oid in nd.get("obligation_refs") or []:
        ob = ob_by_id.get(str(oid))
        if ob and ob.get("statement"):
            criteria.append(str(ob["statement"]))
    title = str(nd.get("title") or node_id)
    if not criteria and title:
        criteria = [title]
    return WorkNode(
        id=node_id,
        title=title,
        done_criteria=criteria,
        repair_streak=int(nd.get("repair_streak") or 0),
        parent_id=nd.get("parent_id"),
        status=str(nd.get("status") or "pending"),
    )
