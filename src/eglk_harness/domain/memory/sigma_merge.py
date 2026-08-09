"""Σ similarity helpers + sibling merge suggestions (never Gate inputs)."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel.tree import TaskTree

def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]{3,}", str(text).lower()) if t}

def text_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)

def sigma_pair_similarity(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    parts_a = " ".join(str(a.get(k) or "") for k in ("cond", "text", "wrong", "correct"))
    parts_b = " ".join(str(b.get(k) or "") for k in ("cond", "text", "wrong", "correct"))
    return text_similarity(parts_a, parts_b)

def suggest_sibling_merges(
    tree: TaskTree,
    active_sigma: Sequence[Mapping[str, Any]],
    *,
    min_sim: float = 0.45,
) -> list[dict[str, Any]]:
    """Suggest merging sibling pending leaves when Σ lessons share themes.

    Output is advisory only (candidates/); Gate never reads it.
    """
    by_leaf: dict[str, list[Mapping[str, Any]]] = {}
    for σ in active_sigma:
        if not isinstance(σ, Mapping):
            continue
        lid = str(σ.get("leaf_id") or "")
        if not lid:
            continue
        by_leaf.setdefault(lid, []).append(σ)

    suggestions: list[dict[str, Any]] = []
    seen_parents: set[str] = set()
    for node, _ in tree.walk():
        if not node.children:
            continue
        if node.id in seen_parents:
            continue
        leaves = [
            c
            for c in node.children
            if not c.children and c.status in {"pending", "in_progress", "admitted"}
        ]
        if len(leaves) < 2:
            continue
        # Pairwise: if two leaves have similar Σ texts, suggest merge of non-admitted pair
        for i, a in enumerate(leaves):
            for b in leaves[i + 1 :]:
                if a.status == "admitted" and b.status == "admitted":
                    continue
                sigs_a = by_leaf.get(a.id) or []
                sigs_b = by_leaf.get(b.id) or []
                best = 0.0
                reason = ""
                for sa in sigs_a:
                    for sb in sigs_b:
                        sim = sigma_pair_similarity(sa, sb)
                        if sim > best:
                            best = sim
                            reason = (
                                f"Σ similarity {sim:.2f} between "
                                f"{sa.get('id')} and {sb.get('id')}"
                            )
                # Also compare done_criteria overlap as weak signal
                if best < min_sim:
                    crit_sim = text_similarity(
                        " ".join(a.done_criteria), " ".join(b.done_criteria)
                    )
                    if crit_sim >= 0.5:
                        best = crit_sim
                        reason = f"done_criteria overlap {crit_sim:.2f}"
                if best < min_sim:
                    continue
                sources = [x.id for x in (a, b) if x.status != "admitted"]
                if len(sources) < 1:
                    continue
                if a.status != "admitted":
                    sources = [a.id] + [x for x in sources if x != a.id]
                union = list(
                    dict.fromkeys([*a.done_criteria, *b.done_criteria])
                )
                suggestions.append(
                    {
                        "event": "merge_suggest",
                        "parent_id": node.id,
                        "nodes": sources if len(sources) >= 2 else [a.id, b.id],
                        "title": f"merged:{a.id}+{b.id}",
                        "done_criteria": union,
                        "reason": reason,
                        "score": best,
                    }
                )
                seen_parents.add(node.id)
                break
            if node.id in seen_parents:
                break
    return suggestions
