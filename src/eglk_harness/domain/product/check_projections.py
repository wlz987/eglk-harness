"""CI pin: code projections must match packaged EXPECTED constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel import gate
from eglk_harness.domain.kernel import scheduler
from eglk_harness.domain.kernel import tree
from eglk_harness.domain.kernel import covers


EXPECTED: dict[str, Any] = {
    "REPAIRS_MAX": 8,
    "COGNITIVE_TOKENS_MAX": 64000,
    "CANDIDATES_MAX": 20,
    "SIGMA_STAGING_MAX": 50,
    "SWARM_BUDGET_FLOOR": 0.10,
    "SPLIT_REPAIR_STREAK": 2,
    "MAX_SPLIT_DEPTH": 4,
    "SPLIT_CHILDREN_MIN": 2,
    "SPLIT_CHILDREN_MAX": 4,
    "EVENT_SCHEMA": "eglk.event",
    "GOAL_SPEC_SCHEMA": "eglk.goal_spec",
    "RUN_PROJECTION_SCHEMA": "eglk.run_projection",
    "QUOTA_SCHEMA": "eglk.quota",
    "INVARIANT_COUNT": 12,
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in self.checks],
            "read_only": True,
            "hitl": False,
            "schema_family": "eglk",
        }


def check_projections() -> ProjectionReport:
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

    for gone in ("TAU_DONE", "TAU_GAP", "TAU_FOCUS", "TAU_UNC", "TAU_UNC_HIGH"):
        report.checks.append(
            ProjectionCheck(
                name=f"removed.{gone}",
                ok=not hasattr(P, gone),
                detail="must not expose float gate/abort thresholds",
            )
        )

    for name in ("tau_focus", "tau_unc", "focus_score", "uncertainty", "usd_used"):
        report.checks.append(
            ProjectionCheck(
                name=f"non_abort.{name}",
                ok=name in P.NON_ABORT_DIAGNOSTIC,
                detail="must never be a sole abort trigger",
            )
        )

    report.checks.append(
        ProjectionCheck(
            name="gate.decide_present",
            ok=getattr(gate, "decide", None) is not None and P.REPAIRS_MAX == EXPECTED["REPAIRS_MAX"],
            detail="gate.decide present; REPAIRS_MAX pinned",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="scheduler.select_ready_node",
            ok=hasattr(scheduler, "select_ready_node") and P.CANDIDATES_MAX == EXPECTED["CANDIDATES_MAX"],
            detail="scheduler present; CANDIDATES_MAX pinned",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="tree.uses_MAX_SPLIT_DEPTH",
            ok=hasattr(tree, "TaskTree") and P.MAX_SPLIT_DEPTH == EXPECTED["MAX_SPLIT_DEPTH"],
            detail="TaskTree present; MAX_SPLIT_DEPTH pinned",
        )
    )

    from pathlib import Path

    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    for name in (
        "event",
        "goal_spec",
        "work_contract",
        "action_claim",
        "evidence_bundle",
        "gate_decision",
        "task_structure",
        "world_transaction",
        "run_projection",
        "quota",
        "memory_record",
        "capability_manifest",
        "run_manifest",
    ):
        report.checks.append(
            ProjectionCheck(
                name=f"schema.{name}",
                ok=(schema_dir / f"{name}.schema.json").is_file(),
                detail=str(schema_dir / f"{name}.schema.json"),
            )
        )

    from eglk_harness.domain import event_store, capability
    from eglk_harness.domain.kernel import advisors, command_handler, reducer, run_engine

    report.checks.append(
        ProjectionCheck(
            name="event_store.module",
            ok=hasattr(event_store, "EventStore"),
            detail="EventStore present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="capability.broker",
            ok=hasattr(capability, "CapabilityBroker"),
            detail="CapabilityBroker present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="command_handler.module",
            ok=hasattr(command_handler, "CommandHandler"),
            detail="CommandHandler present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="reducer.module",
            ok=hasattr(reducer, "reduce_events"),
            detail="reduce_events present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="run_engine.module",
            ok=hasattr(run_engine, "RunEngine"),
            detail="RunEngine present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="advisors.module",
            ok=hasattr(advisors, "run_candidate_selector"),
            detail="CandidateSelector present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="covers.module",
            ok=hasattr(covers, "covers_closure_complete"),
            detail="covers closure present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="scheduler.deps",
            ok=hasattr(scheduler, "deps_satisfied") and hasattr(scheduler, "ready_pool"),
            detail="depends_on-aware ready_pool present",
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
