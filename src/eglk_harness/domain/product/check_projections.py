"""CI pin: code projections must match design/kernel/projections.md SSOT."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel import gate
from eglk_harness.domain.kernel import scheduler
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


def _design_projections_path() -> Path | None:
    root = Path(__file__).resolve().parents[4]
    candidate = root.parent / "design" / "kernel" / "projections.md"
    return candidate if candidate.is_file() else None


def _gate_schema_abort_reasons(schema_path: Path) -> set[str]:
    if not schema_path.is_file():
        return set()
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    then = data.get("then") or {}
    props = then.get("properties") or {}
    reason = props.get("reason") or {}
    enum = reason.get("enum") or []
    return {str(x) for x in enum}


def load_design_projection_constants() -> dict[str, Any]:
    """Parse numeric defaults from design/kernel/projections.md §1–3 tables."""
    path = _design_projections_path()
    if path is None:
        return dict(EXPECTED)
    text = path.read_text(encoding="utf-8")
    out = dict(EXPECTED)
    patterns = {
        "REPAIRS_MAX": r"REPAIRS_MAX.*?`(\d+)`",
        "COGNITIVE_TOKENS_MAX": r"cognitive_tokens_max.*?`(\d+)",
        "CANDIDATES_MAX": r"CANDIDATES_MAX.*?`(\d+)`",
        "SIGMA_STAGING_MAX": r"SIGMA_STAGING_MAX.*?`(\d+)`",
        "SWARM_BUDGET_FLOOR": r"SWARM_BUDGET_FLOOR.*?`([0-9.]+)`",
        "SPLIT_REPAIR_STREAK": r"SPLIT_REPAIR_STREAK.*?`(\d+)`",
        "MAX_SPLIT_DEPTH": r"MAX_SPLIT_DEPTH.*?`(\d+)`",
        "INVARIANT_COUNT": r"不变量条数.*?`(\d+)`",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if not m:
            continue
        val: Any = m.group(1)
        if key == "SWARM_BUDGET_FLOOR":
            out[key] = float(val)
        else:
            out[key] = int(val)
    m_min = re.search(r"SPLIT_CHILDREN_MIN/MAX.*?`(\d+)`.?`(\d+)`", text)
    if m_min:
        out["SPLIT_CHILDREN_MIN"] = int(m_min.group(1))
        out["SPLIT_CHILDREN_MAX"] = int(m_min.group(2))
    return out


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
    design_expected = load_design_projection_constants()
    for key, want in design_expected.items():
        got = actual.get(key)
        report.checks.append(
            ProjectionCheck(
                name=f"design.projections.{key}",
                ok=got == want,
                detail=f"want={want!r} got={got!r}",
            )
        )
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
            name="projections.MAX_SPLIT_DEPTH",
            ok=P.MAX_SPLIT_DEPTH == EXPECTED["MAX_SPLIT_DEPTH"],
            detail="MAX_SPLIT_DEPTH pinned in projections.py",
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
            name="command_handler.commit_split",
            ok=hasattr(command_handler.CommandHandler, "commit_split"),
            detail="split command present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="command_handler.commit_merge",
            ok=hasattr(command_handler.CommandHandler, "commit_merge"),
            detail="merge command present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="command_handler.propose_merge",
            ok=hasattr(command_handler.CommandHandler, "propose_merge"),
            detail="merge proposal command present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="command_handler.propose_split",
            ok=hasattr(command_handler.CommandHandler, "propose_split"),
            detail="split proposal command present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="advisors.mechanical_merge",
            ok=hasattr(advisors, "build_mechanical_merge_candidate"),
            detail="mechanical merge candidate builder present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="scheduler.should_propose_merge",
            ok=hasattr(scheduler, "should_propose_merge"),
            detail="merge trigger heuristic present",
        )
    )
    from eglk_harness.domain.memory import sigma as sigma_mod
    from eglk_harness.domain.kernel import gate as gate_mod

    report.checks.append(
        ProjectionCheck(
            name="sigma.staging_cap",
            ok=hasattr(sigma_mod, "enforce_staging_cap"),
            detail="SIGMA_STAGING_MAX enforcement present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="event_store.no_command_rejected",
            ok="CommandRejected" not in event_store._EVENT_TYPES,
            detail="CommandRejected is diagnostics-only (not EventStore)",
        )
    )
    eglk_pkg = Path(__file__).resolve().parent.parent.parent
    schema_abort = _gate_schema_abort_reasons(eglk_pkg / "domain" / "schemas" / "gate_decision.schema.json")
    report.checks.append(
        ProjectionCheck(
            name="gate.abort_reasons_sync",
            ok=schema_abort == set(gate_mod.ABORT_REASONS),
            detail=f"schema_abort={len(schema_abort)} code={len(gate_mod.ABORT_REASONS)}",
        )
    )
    from eglk_harness.domain.kernel import projection_replay

    report.checks.append(
        ProjectionCheck(
            name="projection_replay.module",
            ok=hasattr(projection_replay, "rebuild_from_events"),
            detail="replay rebuild present",
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
    from eglk_harness.domain.product.observe import dashboard

    report.checks.append(
        ProjectionCheck(
            name="dashboard.read_only",
            ok=callable(dashboard.assert_read_only_routes),
            detail="dashboard routes are GET-only",
        )
    )
    try:
        dashboard.assert_read_only_routes()
        dash_ok = True
        dash_detail = f"routes={len(dashboard.list_routes())}"
    except AssertionError as exc:
        dash_ok = False
        dash_detail = str(exc)
    report.checks.append(
        ProjectionCheck(
            name="dashboard.routes_audit",
            ok=dash_ok,
            detail=dash_detail,
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="reducer.transaction_states",
            ok="transaction_states" in getattr(reducer.ProjectionState, "__dataclass_fields__", {}),
            detail="tx shadow map on projection state",
        )
    )
    from eglk_harness.domain.kernel import context_audit, session_policy, recovery, transaction_audit, run_loop
    from eglk_harness.domain.kernel import gate as gate_mod
    from eglk_harness.domain.plugins import community_plugin_ids
    from eglk_harness.domain.kernel.reducer import apply_event

    report.checks.append(
        ProjectionCheck(
            name="gate.ABORT_REASONS_export",
            ok=hasattr(gate_mod, "ABORT_REASONS") and len(gate_mod.ABORT_REASONS) >= 9,
            detail=f"abort_reasons={len(gate_mod.ABORT_REASONS)}",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="plugins.community_ids",
            ok=len(community_plugin_ids()) >= 1,
            detail=f"plugin_ids={len(community_plugin_ids())}",
        )
    )

    pkg = Path(__file__).resolve().parent.parent.parent  # eglk_harness package root
    for row in context_audit.run_context_audits(pkg):
        report.checks.append(
            ProjectionCheck(name=row["name"], ok=bool(row["ok"]), detail=str(row["detail"]))
        )
    report.checks.append(
        ProjectionCheck(
            name="session_policy.module",
            ok=hasattr(session_policy, "validate_maker_session"),
            detail="fresh session policy present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="recovery.module",
            ok=hasattr(recovery, "reconcile_dangling_transactions"),
            detail="crash recovery present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="run_engine.tick_job_factory",
            ok=hasattr(run_engine.RunEngine, "tick_job_factory"),
            detail="app.run uses RunEngine job factory",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="reducer.apply_event",
            ok=callable(apply_event),
            detail="incremental projection apply present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="run_loop.module",
            ok=hasattr(run_loop, "TickRunLoop"),
            detail="tick orchestration in kernel/run_loop",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="transaction_audit.module",
            ok=hasattr(transaction_audit, "audit_transaction_sequences"),
            detail="tx state machine audit present",
        )
    )
    from eglk_harness.domain.kernel.coverage_proof import validate_merge_obligations

    report.checks.append(
        ProjectionCheck(
            name="coverage_proof.merge_validator",
            ok=callable(validate_merge_obligations),
            detail="merge obligation union validator present",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="transaction_audit.run_aborted_chain",
            ok=callable(transaction_audit.audit_run_aborted_chain),
            detail="RunAborted causation audit present",
        )
    )
    eglk_root = Path(__file__).resolve().parents[4]  # eglk-harness project root
    matrix_test = eglk_root / "tests" / "test_verification_matrix_complete.py"
    ci_script = eglk_root / "scripts" / "ci.sh"
    report.checks.append(
        ProjectionCheck(
            name="verification_matrix.complete_tests",
            ok=matrix_test.is_file(),
            detail=str(matrix_test.name),
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="ci.script",
            ok=ci_script.is_file(),
            detail=str(ci_script.name),
        )
    )
    from eglk_harness.domain.plugins import computer_use as cu_mod

    report.checks.append(
        ProjectionCheck(
            name="plugins.computer_use_module",
            ok=callable(cu_mod.enrich_mcp_allowlist) and callable(cu_mod.doctor_computer_use_detail),
            detail="universal computer-use facade present",
        )
    )
    frag = (
        Path(__file__).resolve().parent.parent
        / "memory"
        / "skills"
        / "fragments"
        / "computer_use.md"
    )
    report.checks.append(
        ProjectionCheck(
            name="skills.computer_use_fragment",
            ok=frag.is_file(),
            detail=str(frag.name),
        )
    )
    from eglk_harness.domain.eval.paths import default_eval_root as eval_default_root
    from eglk_harness.domain.runtime import boundary_verify as bv_mod
    from eglk_harness.domain.runtime import swarm_context as swarm_ctx_mod

    report.checks.append(
        ProjectionCheck(
            name="eval.default_eval_root_no_bundled",
            ok=eval_default_root() is None or os.environ.get("EGLK_EVAL_ROOT"),
            detail="no silent bundled_eval when EGLK_EVAL_ROOT unset",
        )
    )
    swarm_src = Path(swarm_ctx_mod.__file__).read_text(encoding="utf-8")
    report.checks.append(
        ProjectionCheck(
            name="swarm_context.generic_env_probes",
            ok="env_probe_prior_rows" in swarm_src and "probe_wa_sites" not in swarm_src,
            detail="SWARM priors via eval connector hook",
        )
    )
    bv_src = Path(bv_mod.__file__).read_text(encoding="utf-8")
    report.checks.append(
        ProjectionCheck(
            name="boundary.no_wa_hint_filename",
            ok="wa_hard_agent_response_hint" not in bv_src,
            detail="deliverable hints use generic paths only",
        )
    )
    report.checks.append(
        ProjectionCheck(
            name="boundary.no_audit_progress_clamp",
            ok="audit_progress" not in bv_src,
            detail="boundary violations use additional_gaps",
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
