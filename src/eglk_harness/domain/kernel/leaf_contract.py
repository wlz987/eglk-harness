"""Assemble Leaf Contract from tree node + optional prior context."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel.tree import TreeNode


@dataclass
class LeafContract:
    leaf_id: str
    goal: str
    acceptance: list[str]
    boundary: list[str] = field(default_factory=list)
    prior_evidence: list[Any] = field(default_factory=list)
    tick: int | None = None
    parent_id: str | None = None
    attempt_index: int | None = None
    learned_skills_block: str = ""
    goal_md_excerpt: str = ""
    goal_format_excerpt: str = ""
    root_acceptance: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # drop Nones / empty optional strings for cleaner JSON
        return {k: v for k, v in d.items() if v is not None and v != "" and v != []}

    def _goal_context_lines(self) -> list[str]:
        if not (self.goal_md_excerpt or self.goal_format_excerpt):
            return []
        from eglk_harness.domain.kernel.compile_goal import render_goal_dual_block

        return ["", render_goal_dual_block(self.goal_md_excerpt, self.goal_format_excerpt)]

    def render_maker_block(self) -> str:
        lines = [
            "[LEAF_CONTRACT]",
            f"leaf_id: {self.leaf_id}",
            f"goal: {self.goal}",
            f"tick: {self.tick if self.tick is not None else 0}",
            "acceptance:",
            *[f"  - {a}" for a in self.acceptance],
            "boundary:",
        ]
        if self.boundary:
            lines.extend(f"  - {b}" for b in self.boundary)
        else:
            lines.append("  - (none)")
        if self.root_acceptance and self.leaf_id != "root":
            lines.append("root_acceptance (whole-task — still required for root admit):")
            lines.extend(f"  - {a}" for a in self.root_acceptance)
        lines.append("prior_evidence:")
        for p in self.prior_evidence:
            if isinstance(p, Mapping):
                lines.append(f"  - [{p.get('kind', 'other')}] {p.get('text', '')}")
            else:
                lines.append(f"  - {p}")
        if not self.prior_evidence:
            lines.append("  - (none)")
        lines.extend(self._goal_context_lines())
        if self.learned_skills_block:
            lines.extend(["", self.learned_skills_block])
        return "\n".join(lines)

    def render_checker_block(self) -> str:
        """Checker sees acceptance/boundary; prior only as titles/ids."""
        lines = [
            "[LEAF_CONTRACT]",
            f"leaf_id: {self.leaf_id}",
            f"goal: {self.goal}",
            f"tick: {self.tick if self.tick is not None else 0}",
            "acceptance:",
            *[f"  - {a}" for a in self.acceptance],
            "boundary:",
        ]
        if self.boundary:
            lines.extend(f"  - {b}" for b in self.boundary)
        else:
            lines.append("  - (none)")
        if self.root_acceptance and self.leaf_id != "root":
            lines.append("root_acceptance (whole-task):")
            lines.extend(f"  - {a}" for a in self.root_acceptance)
        lines.append("prior_evidence (titles only):")
        for p in self.prior_evidence:
            if isinstance(p, Mapping):
                ref = p.get("ref") or p.get("kind") or ""
                text = str(p.get("text", ""))[:80]
                lines.append(f"  - {ref}: {text}")
            else:
                lines.append(f"  - {str(p)[:80]}")
        if not self.prior_evidence:
            lines.append("  - (none)")
        lines.extend(self._goal_context_lines())
        return "\n".join(lines)


def assemble_leaf_contract(
    leaf: TreeNode,
    *,
    tick: int | None = None,
    boundary: Sequence[str] | None = None,
    prior_evidence: Sequence[Any] | None = None,
    goal_constraints: Sequence[str] | None = None,
    sigma_lessons: Sequence[Mapping[str, Any]] | None = None,
    skill_hints: Sequence[str] | None = None,
    learned_skills_block: str = "",
    goal_md_excerpt: str = "",
    goal_format_excerpt: str = "",
    root_acceptance: Sequence[str] | None = None,
) -> LeafContract:
    """Build a LeafContract for an in_progress (or any) leaf node.

    Raises ValueError if done_criteria empty (assembly failure → must not start Maker).
    """
    if not leaf.done_criteria:
        raise ValueError(f"leaf {leaf.id} missing done_criteria; cannot assemble contract")

    bounds = [str(x) for x in (boundary or [])]
    for c in goal_constraints or []:
        if c not in bounds:
            bounds.append(str(c))
    for hint in skill_hints or []:
        line = str(hint)
        if line and line not in bounds:
            bounds.append(line)
    for lesson in sigma_lessons or []:
        if not isinstance(lesson, Mapping):
            continue
        text = str(lesson.get("text") or lesson.get("cond") or "")
        if text:
            line = f"Σ:{text[:120]}"
            if line not in bounds:
                bounds.append(line)

    priors: list[Any] = list(prior_evidence or [])
    for ch in leaf.verifier_challenges:
        priors.append({"kind": "challenge", "text": ch, "ref": leaf.id})

    attempt = leaf.repair_streak  # attempts so far; caller may override via field
    return LeafContract(
        leaf_id=leaf.id,
        goal=leaf.title,
        acceptance=list(leaf.done_criteria),
        boundary=bounds,
        prior_evidence=priors,
        tick=tick,
        parent_id=leaf.parent_id,
        attempt_index=attempt,
        learned_skills_block=learned_skills_block.strip(),
        goal_md_excerpt=goal_md_excerpt.strip(),
        goal_format_excerpt=goal_format_excerpt.strip(),
        root_acceptance=[str(x) for x in (root_acceptance or []) if str(x).strip()],
    )


def contract_from_dict(data: Mapping[str, Any]) -> LeafContract:
    """Rebuild ``LeafContract`` from tick-assembled JSON."""
    acceptance = data.get("acceptance")
    boundary = data.get("boundary")
    prior = data.get("prior_evidence")
    root_acc = data.get("root_acceptance")
    return LeafContract(
        leaf_id=str(data.get("leaf_id") or "root"),
        goal=str(data.get("goal") or ""),
        acceptance=[str(x) for x in acceptance if str(x).strip()] if isinstance(acceptance, list) else [],
        boundary=[str(x) for x in boundary if str(x).strip()] if isinstance(boundary, list) else [],
        prior_evidence=list(prior) if isinstance(prior, list) else [],
        tick=int(data["tick"]) if data.get("tick") is not None else None,
        parent_id=str(data["parent_id"]) if data.get("parent_id") else None,
        attempt_index=int(data["attempt_index"]) if data.get("attempt_index") is not None else None,
        learned_skills_block=str(data.get("learned_skills_block") or ""),
        goal_md_excerpt=str(data.get("goal_md_excerpt") or ""),
        goal_format_excerpt=str(data.get("goal_format_excerpt") or ""),
        root_acceptance=[str(x) for x in root_acc if str(x).strip()] if isinstance(root_acc, list) else [],
    )
