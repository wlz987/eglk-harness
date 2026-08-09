"""Dynamic task tree state machine (structure + mechanical status writes)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

from eglk_harness.domain.kernel import projections as P

NodeStatus = str  # pending|in_progress|admitted|failed|split|merged

@dataclass
class TreeNode:
    id: str
    title: str
    status: NodeStatus
    done_criteria: list[str]
    children: list[TreeNode] = field(default_factory=list)
    parent_id: str | None = None
    split_from: str | None = None
    merged_from: list[str] = field(default_factory=list)
    verifier_challenges: list[str] = field(default_factory=list)
    repair_streak: int = 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "done_criteria": list(self.done_criteria),
            "children": [c.to_dict() for c in self.children],
            "parent_id": self.parent_id,
            "repair_streak": self.repair_streak,
        }
        if self.split_from is not None:
            d["split_from"] = self.split_from
        if self.merged_from:
            d["merged_from"] = list(self.merged_from)
        if self.verifier_challenges:
            d["verifier_challenges"] = list(self.verifier_challenges)
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TreeNode:
        children = [cls.from_dict(c) for c in data.get("children") or []]
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            status=str(data.get("status", "pending")),
            done_criteria=[str(x) for x in data.get("done_criteria") or []],
            children=children,
            parent_id=data.get("parent_id"),
            split_from=data.get("split_from"),
            merged_from=[str(x) for x in data.get("merged_from") or []],
            verifier_challenges=[str(x) for x in data.get("verifier_challenges") or []],
            repair_streak=int(data.get("repair_streak") or 0),
        )

@dataclass
class TaskTree:
    root: TreeNode

    def to_document(self) -> dict[str, Any]:
        return {"subgoals_tree": self.root.to_dict()}

    @classmethod
    def from_document(cls, doc: Mapping[str, Any]) -> TaskTree:
        raw = doc.get("subgoals_tree") if "subgoals_tree" in doc else doc
        assert isinstance(raw, Mapping)
        return cls(root=TreeNode.from_dict(raw))

    def walk(self) -> Iterator[tuple[TreeNode, int]]:
        def _walk(n: TreeNode, depth: int) -> Iterator[tuple[TreeNode, int]]:
            yield n, depth
            for c in n.children:
                yield from _walk(c, depth + 1)

        yield from _walk(self.root, 0)

    def find(self, node_id: str) -> TreeNode | None:
        for n, _ in self.walk():
            if n.id == node_id:
                return n
        return None

    def depth_of(self, node_id: str) -> int | None:
        for n, d in self.walk():
            if n.id == node_id:
                return d
        return None

    def leaves(self) -> list[TreeNode]:
        return [n for n, _ in self.walk() if not n.children and n.status not in {"split", "merged"}]

    def in_progress(self) -> TreeNode | None:
        for n, _ in self.walk():
            if n.status == "in_progress":
                return n
        return None

    def ensure_pointer(self) -> TreeNode | None:
        """Ensure exactly one in_progress leaf when work remains; return it."""
        cur = self.in_progress()
        if cur is not None:
            return cur
        for n in self.leaves():
            if n.status == "pending":
                n.status = "in_progress"
                return n
        return None

    def admit_current(self) -> TreeNode | None:
        """Mark in_progress leaf admitted; advance next pending leaf. Returns admitted node."""
        cur = self.in_progress()
        if cur is None:
            return None
        cur.status = "admitted"
        cur.repair_streak = 0
        self._maybe_admit_ancestors(cur)
        self.ensure_pointer()
        return cur

    def _maybe_admit_ancestors(self, node: TreeNode) -> None:
        """If all leaf descendants under a subtree are admitted, mark internals admitted."""
        # Recompute from root: any non-split/merged node with children all terminal-success
        for n, _ in self.walk():
            if not n.children:
                continue
            if n.status in {"merged", "failed"}:
                continue
            # ``split`` parents may still become admitted once all work leaves succeed.
            leaf_like = [c for c in self._descendant_work_nodes(n)]
            if leaf_like and all(c.status == "admitted" for c in leaf_like):
                n.status = "admitted"

    def _descendant_work_nodes(self, node: TreeNode) -> list[TreeNode]:
        out: list[TreeNode] = []

        def walk(n: TreeNode) -> None:
            if not n.children:
                if n.status not in {"split", "merged"}:
                    out.append(n)
                return
            for c in n.children:
                walk(c)

        walk(node)
        return out

    def all_work_admitted(self) -> bool:
        work = [n for n in self.leaves()]
        return bool(work) and all(n.status == "admitted" for n in work)

    def repair_current(self) -> TreeNode | None:
        """Gate repair: leaf → pending, streak++, clear in_progress."""
        cur = self.in_progress()
        if cur is None:
            return None
        cur.repair_streak += 1
        cur.status = "pending"
        return cur

    def should_split(self, node: TreeNode | None = None) -> bool:
        n = node or self.in_progress() or self.find_pending_with_streak()
        if n is None:
            return False
        depth = self.depth_of(n.id)
        if depth is None or depth >= P.MAX_SPLIT_DEPTH:
            return False
        return n.repair_streak >= P.SPLIT_REPAIR_STREAK

    def find_pending_with_streak(self) -> TreeNode | None:
        for n in self.leaves():
            if n.status == "pending" and n.repair_streak >= P.SPLIT_REPAIR_STREAK:
                return n
        return None

    def split_node(
        self,
        node_id: str,
        children_spec: list[Mapping[str, Any]],
    ) -> TreeNode:
        """Mark node split; attach children as pending; set first child in_progress.

        ``children_spec`` items: {id, title, done_criteria}.
        """
        node = self.find(node_id)
        if node is None:
            raise KeyError(node_id)
        depth = self.depth_of(node_id) or 0
        if depth >= P.MAX_SPLIT_DEPTH:
            raise ValueError(f"MAX_SPLIT_DEPTH={P.MAX_SPLIT_DEPTH} exceeded for {node_id}")
        if not (P.SPLIT_CHILDREN_MIN <= len(children_spec) <= P.SPLIT_CHILDREN_MAX):
            raise ValueError(
                f"split children count must be {P.SPLIT_CHILDREN_MIN}..{P.SPLIT_CHILDREN_MAX}"
            )

        node.status = "split"
        node.children = []
        for i, spec in enumerate(children_spec):
            child = TreeNode(
                id=str(spec["id"]),
                title=str(spec["title"]),
                status="in_progress" if i == 0 else "pending",
                done_criteria=[str(x) for x in spec.get("done_criteria") or []],
                parent_id=node.id,
                split_from=node.id,
                repair_streak=0,
            )
            if not child.done_criteria:
                raise ValueError(f"child {child.id} missing done_criteria")
            node.children.append(child)
        return node

    def fail_current(self) -> TreeNode | None:
        cur = self.in_progress()
        if cur is None:
            return None
        cur.status = "failed"
        return cur

    def merge_sibling_leaves(
        self,
        *,
        parent_id: str,
        source_ids: list[str],
        new_id: str,
        title: str,
        done_criteria: list[str],
    ) -> TreeNode:
        """Mark source leaves ``merged`` (kept for audit); append a new ``pending`` sibling.

        Sources must be leaf children of ``parent_id``. Does not delete nodes.
        """
        parent = self.find(parent_id)
        if parent is None:
            raise KeyError(parent_id)
        if not done_criteria:
            raise ValueError("merge requires non-empty done_criteria")
        if len(source_ids) < 1:
            raise ValueError("merge requires ≥1 source leaf")
        if self.find(new_id) is not None:
            raise ValueError(f"merge target id already exists: {new_id}")

        sources: list[TreeNode] = []
        for sid in source_ids:
            node = self.find(sid)
            if node is None:
                raise KeyError(sid)
            if node.parent_id != parent_id:
                raise ValueError(f"{sid} is not a child of {parent_id}")
            if node.children:
                raise ValueError(f"{sid} is not a leaf")
            if node.status in {"merged", "split", "failed"}:
                raise ValueError(f"{sid} status={node.status} cannot merge")
            sources.append(node)

        for node in sources:
            node.status = "merged"

        child = TreeNode(
            id=new_id,
            title=title,
            status="pending",
            done_criteria=[str(x) for x in done_criteria],
            parent_id=parent_id,
            merged_from=list(source_ids),
            repair_streak=0,
        )
        parent.children.append(child)
        return child

    def try_merge_siblings_after_admit(self, admitted_id: str) -> dict[str, Any] | None:
        """Structural overlap merge (task_tree merge contract).

        After a leaf is admitted: pending/in_progress sibling leaves whose
        ``done_criteria`` intersect the admitted leaf are collapsed into one
        new pending sibling. The admitted leaf stays ``admitted``.
        """
        admitted = self.find(admitted_id)
        if admitted is None or admitted.status != "admitted":
            return None
        if admitted.parent_id is None:
            return None
        parent = self.find(admitted.parent_id)
        if parent is None:
            return None

        admitted_crit = {_norm_crit(c) for c in admitted.done_criteria}
        if not admitted_crit:
            return None

        to_merge: list[TreeNode] = []
        for sib in parent.children:
            if sib.id == admitted_id:
                continue
            if sib.children:
                continue
            if sib.status not in {"pending", "in_progress"}:
                continue
            sib_crit = {_norm_crit(c) for c in sib.done_criteria}
            if admitted_crit & sib_crit:
                to_merge.append(sib)
        if not to_merge:
            return None

        source_ids = [n.id for n in to_merge]
        union: list[str] = []
        seen: set[str] = set()
        for c in list(admitted.done_criteria) + [c for n in to_merge for c in n.done_criteria]:
            key = _norm_crit(c)
            if key in seen:
                continue
            seen.add(key)
            union.append(c)
        new_id = f"{parent.id}.m{len(parent.children) + 1}"
        title = f"merged:{','.join(source_ids)}"
        # Clear in_progress among sources before merge (they become merged)
        was_pointer = any(n.status == "in_progress" for n in to_merge)
        self.merge_sibling_leaves(
            parent_id=parent.id,
            source_ids=source_ids,
            new_id=new_id,
            title=title,
            done_criteria=union,
        )
        if was_pointer or self.in_progress() is None:
            self.ensure_pointer()
        return {
            "event": "merge",
            "nodes": source_ids,
            "into": new_id,
            "kept_admitted": admitted_id,
            "reason": "done_criteria overlap with admitted sibling",
        }

    def clone(self) -> TaskTree:
        return TaskTree.from_document(deepcopy(self.to_document()))

def _norm_crit(text: str) -> str:
    return " ".join(str(text).lower().split())

def make_root(title: str, done_criteria: list[str], *, leaf: bool = True) -> TaskTree:
    """Create a minimal tree: root as single in_progress leaf, or root with no work yet."""
    root = TreeNode(
        id="root",
        title=title,
        status="in_progress" if leaf else "pending",
        done_criteria=list(done_criteria),
        children=[],
        parent_id=None,
    )
    return TaskTree(root=root)
