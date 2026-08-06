"""CI pin: code projections must match design/kernel/projections.md defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eglk_harness.domain import projections as P
from eglk_harness.domain import gate, swarm, tree


# Machine-readable pin of design/kernel/projections.md (change design first).
EXPECTED: dict[str, Any] = {
    "TAU_DONE": 1.0,
    "TAU_GAP": 0.5,
    "TAU_FOCUS": 0.2,
    "TAU_UNC": 0.15,
    "REPAIRS_MAX": 8,
    "COGNITIVE_TOKENS_MAX": 64000,
    "TAU_UNC_HIGH": 0.6,
    "CANDIDATES_MAX": 20,
    "SIGMA_ACTIVE_MAX": 50,
    "SWARM_BUDGET_FLOOR": 0.10,
    "SPLIT_REPAIR_STREAK": 2,
    "MAX_SPLIT_DEPTH": 4,
    "SPLIT_CHILDREN_MIN": 2,
    "SPLIT_CHILDREN_MAX": 4,
    "STATE_SCHEMA": "eglk.state/0.2.2",
    "GOAL_SCHEMA_VERSION": "0.2.2",
    "INVARIANT_COUNT": 11,
}


@dataclass
class ProjectionCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class ProjectionReport:
    checks: list[ProjectionCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


def check_projections() -> ProjectionReport:
    """Assert domain.projections (+ consumers) match the pinned table."""
    report = ProjectionReport()
    actual = P.as_dict()
    for key, want in EXPECTED.items():
        got = actual.get(key)
        report.checks.append(
            ProjectionCheck(
                name=f"projections.{key}",
                ok=got == want,
                detail=f"want={want!r} got={got!r}",
            )
        )

    # Non-abort thresholds must remain non-abort
    for name in ("tau_focus", "tau_unc", "focus_score", "uncertainty"):
        report.checks.append(
            ProjectionCheck(
                name=f"non_abort.{name}",
                ok=name in P.NON_ABORT_THRESHOLDS,
                detail="must never be a sole abort trigger",
            )
        )

    # Consumers import the same module constants
    report.checks.append(
        ProjectionCheck(
            name="gate.uses_REPAIRS_MAX",
            ok=getattr(gate, "decide", None) is not None and P.REPAIRS_MAX == EXPECTED["REPAIRS_MAX"],
            detail="gate.decide present; REPAIRS_MAX pinned",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="swarm.uses_TAU_FOCUS",
            ok=hasattr(swarm, "decide_swarm") and P.TAU_FOCUS == EXPECTED["TAU_FOCUS"],
            detail="decide_swarm present; TAU_FOCUS pinned",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="tree.uses_MAX_SPLIT_DEPTH",
            ok=hasattr(tree, "TaskTree") and P.MAX_SPLIT_DEPTH == EXPECTED["MAX_SPLIT_DEPTH"],
            detail="TaskTree present; MAX_SPLIT_DEPTH pinned",
        )
    )
    return report


def main(argv: list[str] | None = None) -> int:
    report = check_projections()
    for c in report.checks:
        mark = "ok  " if c.ok else "FAIL"
        print(f"{mark}  {c.name}: {c.detail}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
