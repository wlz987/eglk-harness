"""Governor split proposals — partition leaf acceptance into child leaves."""

from __future__ import annotations

import re
from typing import Any, Sequence

from eglk_harness.domain.kernel import projections as P

# Tool-API / type-assert micro-leaves that derail goal-level work (reject → fallback).
_TOOL_MICRO_RE = re.compile(
    r"(?:"
    r"session_id|isinstance\s*\(|"
    r"returns a JSON response|non-empty string\s*\(length|"
    r"len\s*\(\s*response|"
    r"assert\s+response|"
    r"invoke\s+\w+_|\bcall\s+\w+_|"  # invoke/call tool_xyz style
    r"\bstart_session\b|\bfinalize_session\b|"
    r"tool smoke|smoke test the (?:mcp|tool)"
    r")",
    re.IGNORECASE,
)


def looks_like_tool_micro_criteria(criteria: Sequence[str]) -> bool:
    """True when criteria obsess over tool wiring instead of goal deliverables."""
    if not criteria:
        return False
    hits = sum(1 for c in criteria if _TOOL_MICRO_RE.search(str(c)))
    return hits >= max(1, (len(criteria) + 1) // 2)


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
    ``part A/B done`` placeholders. Never invents tool-API micro-leaves.
    """
    _ = repair_streak
    criteria = [str(c).strip() for c in done_criteria if str(c).strip()]
    if not criteria:
        criteria = [f"Complete: {title}"]

    max_c = P.SPLIT_CHILDREN_MAX
    min_c = P.SPLIT_CHILDREN_MIN

    if len(criteria) == 1:
        # Single criterion → implement + independently verify (same criterion, not tool asserts)
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
        if len(criteria) <= max_c:
            groups = [[c] for c in criteria]
        else:
            groups = _chunk(criteria, parts=max_c)
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

    if len(children) > max_c:
        children = children[:max_c]
    if len(children) < min_c and len(criteria) >= 1:
        pass

    return [
        {
            "id": c["id"],
            "title": c["title"],
            "done_criteria": c["done_criteria"],
        }
        for c in children
    ]


def sanitize_governor_children(
    children: Sequence[MappingLike],
    *,
    leaf_id: str,
    title: str,
    parent_criteria: Sequence[str],
) -> list[dict[str, Any]] | None:
    """Return cleaned children, or None to signal fallback to mechanical propose_children.

    Rejects proposals that invent tool-session micro-criteria unrelated to parent acceptance.
    """
    out: list[dict[str, Any]] = []
    for i, c in enumerate(children, start=1):
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or f"{leaf_id}.{i:02d}")
        ctitle = str(c.get("title") or cid)
        crit = c.get("done_criteria") or c.get("acceptance") or []
        if not isinstance(crit, list) or not crit:
            continue
        crit_s = [str(x) for x in crit if str(x).strip()]
        if not crit_s:
            continue
        if looks_like_tool_micro_criteria(crit_s):
            return None
        out.append({"id": cid, "title": ctitle, "done_criteria": crit_s})
    if len(out) < P.SPLIT_CHILDREN_MIN:
        return None
    if len(out) > P.SPLIT_CHILDREN_MAX:
        out = out[: P.SPLIT_CHILDREN_MAX]
    # If parent had real criteria and none of the children share any token overlap,
    # still allow — but prefer parent partition when children look alien.
    parent = [str(x).strip().lower() for x in parent_criteria if str(x).strip()]
    if parent:
        parent_blob = " ".join(parent)
        alien = 0
        for ch in out:
            blob = " ".join(x.lower() for x in ch["done_criteria"])
            # crude: require at least one significant word overlap (>4 chars) with parent
            words = {w for w in re.findall(r"[a-z0-9_]{5,}", parent_blob)}
            if words and not any(w in blob for w in words):
                alien += 1
        if alien == len(out):
            return None
    _ = title
    return out


# typing alias without importing Mapping everywhere for py3.10
MappingLike = Any


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
        "source": "mechanical",
    }
