"""Governor split proposals — partition leaf acceptance into child leaves."""

from __future__ import annotations

from typing import Any, Sequence

from eglk_harness.domain import projections as P


def _chunk(items: list[str], *, parts: int) -> list[list[str]]:
    if parts <= 1 or not items:
        return [list(items)] if items else []
    parts = min(parts, len(items))
    size = max(1, (len(items) + parts - 1) // parts)
    return [items[i : i + size] for i in range(0, len(items), size)]


def propose_children(
    leaf_id: str,
    title: str,
    done_criteria: Sequence[str],
    *,
    repair_streak: int = 0,
) -> list[dict[str, Any]]:
    """Build 2..SPLIT_CHILDREN_MAX children from acceptance criteria.

    Mechanical (no LLM): when a leaf stalls (repair streak), split by criteria
    groups so the next Maker faces a smaller contract. Never emits generic
    ``part A/B done`` placeholders.
    """
    criteria = [str(c).strip() for c in done_criteria if str(c).strip()]
    if not criteria:
        criteria = [f"Complete: {title}"]

    max_c = P.SPLIT_CHILDREN_MAX
    min_c = P.SPLIT_CHILDREN_MIN

    if len(criteria) == 1:
        # Single criterion → implement + independently verify
        only = criteria[0]
        children = [
            {
                "id": f"{leaf_id}.01",
                "title": f"Implement: {title}",
                "done_criteria": [only],
            },
            {
                "id": f"{leaf_id}.02",
                "title": f"Verify: {title}",
                "done_criteria": [
                    f"Independently verify: {only}",
                    "Record concrete artifacts proving the criterion holds",
                ],
            },
        ]
    else:
        # Prefer one criterion per child when few; otherwise chunk.
        if len(criteria) <= max_c:
            groups = [[c] for c in criteria]
        else:
            groups = _chunk(criteria, parts=max_c)
        while len(groups) < min_c and len(criteria) >= min_c:
            # shouldn't happen with chunk; keep invariant
            break
        children = []
        for i, group in enumerate(groups, start=1):
            head = group[0]
            short = head if len(head) <= 72 else head[:69] + "..."
            children.append(
                {
                    "id": f"{leaf_id}.{i:02d}",
                    "title": f"{title} · {short}",
                    "done_criteria": list(group),
                }
            )

    # Cap / pad to projection bounds
    if len(children) > max_c:
        children = children[:max_c]
    if len(children) < min_c and len(criteria) >= 1:
        # already handled single-criterion as 2 children
        pass

    # Annotate split context (non-schema extras stripped by TreeNode.from_dict if unknown —
    # keep only id/title/done_criteria for split_node)
    return [
        {
            "id": c["id"],
            "title": c["title"],
            "done_criteria": c["done_criteria"],
        }
        for c in children
    ]


def proposal_document(
    *,
    tick: int,
    leaf_id: str,
    title: str,
    done_criteria: Sequence[str],
    repair_streak: int = 0,
) -> dict[str, Any]:
    return {
        "role": "governor",
        "tick": tick,
        "split_node": leaf_id,
        "repair_streak": repair_streak,
        "children": propose_children(
            leaf_id, title, done_criteria, repair_streak=repair_streak
        ),
    }
