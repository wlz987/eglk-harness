"""Mechanical CoverageProof validation for split/merge commands."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def validate_split_coverage(
    *,
    parent_obligation_ids: Sequence[str],
    child_obligation_map: Mapping[str, Sequence[str]],
    proof_kind: str,
    opened_obligations: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[bool, str]:
    """Return (ok, reason). See design/kernel/task_tree.md §2."""
    parents = [str(x) for x in parent_obligation_ids if str(x)]
    if not parents:
        return False, "empty_parent_obligations"
    kind = str(proof_kind or "partition")
    if kind not in {"partition", "refinement"}:
        return False, "invalid_proof_kind"

    assigned: set[str] = set()
    for child_ids in child_obligation_map.values():
        for oid in child_ids:
            assigned.add(str(oid))

    if kind == "partition":
        if not child_obligation_map:
            return False, "empty_child_map"
        if not all(p in assigned for p in parents):
            return False, "partition_incomplete"
        return True, "ok"

    # refinement: opened derived obligations must cover each parent via parent_obligation_id
    opened = list(opened_obligations or [])
    if not opened:
        return False, "refinement_missing_opened"
    derived_by_parent: dict[str, set[str]] = {}
    for ob in opened:
        if not isinstance(ob, Mapping):
            continue
        pid = ob.get("parent_obligation_id")
        oid = ob.get("id")
        if pid is None or not oid:
            return False, "opened_missing_parent_link"
        derived_by_parent.setdefault(str(pid), set()).add(str(oid))
    for p in parents:
        if p not in derived_by_parent:
            return False, f"parent_not_refined:{p}"
    return True, "ok"


def validate_merge_obligations(
    *,
    source_obligation_sets: Sequence[Sequence[str]],
    merged_obligation_refs: Sequence[str],
    satisfied_obligation_ids: Sequence[str],
) -> tuple[bool, str]:
    """Merge must retain all source obligations; satisfied must remain satisfied."""
    union: set[str] = set()
    for refs in source_obligation_sets:
        union.update(str(x) for x in refs)
    merged = {str(x) for x in merged_obligation_refs}
    if union != merged:
        return False, "obligation_union_mismatch"
    sat = {str(x) for x in satisfied_obligation_ids}
    for oid in sat:
        if oid in union and oid not in merged:
            return False, "satisfied_obligation_dropped"
    return True, "ok"
