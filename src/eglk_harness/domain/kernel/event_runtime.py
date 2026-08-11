"""Run-time event authority — shared by TickJob and RunEngine."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.capability import CapabilityBroker, ensure_manifest
from eglk_harness.domain.environment.world_transaction import (
    LocalFilesystemAdapter,
    WorldTransaction,
    ceiling_class,
)
from eglk_harness.domain.event_store import open_store
from eglk_harness.domain.kernel.command_handler import CommandHandler, CommandResult
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.projections import (
    effective_cognitive_tokens_max,
    effective_repairs_max,
)
from eglk_harness.domain.kernel.recovery import reconcile_dangling_transactions
from eglk_harness.domain.kernel.projection_mirror import mirror_audit_artifacts
from eglk_harness.domain.kernel.projection_replay import projection_diff, rebuild_from_events
from eglk_harness.domain.kernel.run_engine import compile_goal_spec
from eglk_harness.domain.kernel.scheduler import assemble_work_contract, select_ready_node
from eglk_harness.domain.kernel.projection_view import projection_root_done
from eglk_harness.domain.kernel import worldref
from eglk_harness.domain.memory.lifecycle import digest_active_snapshot
from eglk_harness.domain.memory.memory_policy import bootstrap_frozen_digest, eval_freeze_memory


class RunEventContext:
    """EventStore + CommandHandler + world adapter for one loop goal."""

    def __init__(self, workdir: Path, goal_id: str) -> None:
        self.workdir = Path(workdir).resolve()
        self.goal_id = goal_id
        self.loop_dir = paths.ensure_loop_layout(self.workdir, goal_id)
        paths.ensure_memory_layout(self.workdir)
        self.store = open_store(self.loop_dir)
        manifest = ensure_manifest(paths.capability_manifest_path(self.workdir))
        self.broker = CapabilityBroker(manifest)
        self.handler = CommandHandler(self.store, broker=self.broker)
        self.env = LocalFilesystemAdapter(self.workdir, self.loop_dir / "world")
        self._active_tx: WorldTransaction | None = None
        self._active_contract: dict[str, Any] | None = None

    def acquire(self) -> None:
        self.handler.acquire()
        reconcile_dangling_transactions(self.handler, workdir=self.workdir, env=self.env)
        self.handler.check_goal_drift(self.workdir)

    def release(self) -> None:
        self.handler.release()

    def close(self) -> None:
        try:
            self.release()
        finally:
            self.store.close()

    def bootstrap_if_needed(
        self,
        *,
        goal_title: str,
        done_criteria: list[str],
    ) -> None:
        self.handler.verify_or_fault()
        proj = self.handler.projection()
        if proj.run_status in {"succeeded", "aborted", "invalid", "faulted"}:
            return
        drift = self.handler.check_goal_drift(self.workdir)
        if not drift.ok:
            return
        if proj.last_sequence >= 0 and proj.run_status not in {"created", ""}:
            if proj.run_status == "validating":
                self.handler.node_ready(proj.root_id or "root")
            return

        goal_path = paths.goal_path(self.workdir)
        goal_text = goal_path.read_text(encoding="utf-8") if goal_path.is_file() else goal_title
        if eval_freeze_memory():
            mem = bootstrap_frozen_digest(self.workdir) or digest_active_snapshot(self.workdir)
        else:
            mem = digest_active_snapshot(self.workdir)
        self.handler.run_created(
            goal_id=self.goal_id,
            memory_digest=mem,
            capability_manifest_ref=str(paths.capability_manifest_path(self.workdir)),
            cognitive_tokens_max=effective_cognitive_tokens_max(),
            repairs_max=effective_repairs_max(),
        )
        spec = compile_goal_spec(
            self.workdir,
            goal_id=self.goal_id,
            goal_text=goal_text,
            done_criteria=done_criteria,
        )
        proj_dir = paths.projections_dir(self.workdir, self.goal_id)
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "goal_spec.json").write_text(
            json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        ob_ids = [o["id"] for o in spec["requirements"][0]["obligations"]]
        self.handler.goal_compiled(
            {
                "goal_spec_ref": "projections/goal_spec.json",
                "source_digest": spec["source_digest"],
                "root_node_id": "root",
                "title": goal_title,
                "obligation_refs": ob_ids,
                "obligations": spec["requirements"][0]["obligations"],
            }
        )
        self.handler.node_ready("root")

    def export_projections(self, *, tick: int | None = None) -> dict[str, Any]:
        exported = self.handler.export_projections()
        proj_dir = paths.projections_dir(self.workdir, self.goal_id)
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "run_projection.json").write_text(
            json.dumps(exported["run"], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if exported.get("task_structure"):
            (proj_dir / "task_structure.json").write_text(
                json.dumps(exported["task_structure"], indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        if exported.get("obligation_ledger"):
            (proj_dir / "obligation_ledger.json").write_text(
                json.dumps(exported["obligation_ledger"], indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        # Replay equivalence check — projections must match pure rebuild.
        replayed = rebuild_from_events(self.loop_dir)
        drift = projection_diff(exported["run"], replayed["run"])
        if drift and self.handler.projection().run_status not in {
            "faulted",
            "succeeded",
            "aborted",
            "invalid",
        }:
            self.handler.run_faulted(
                reason="projection_drift",
                detail=";".join(drift[:5]),
            )
        mirror_audit_artifacts(
            self.loop_dir,
            self.store.read_all(),
            tick=tick,
        )
        return exported

    def projection(self):
        return self.handler.projection()

    def select_node_id(self) -> str | None:
        return select_ready_node(self.handler.projection())

    def assemble_contract_for_node(self, node_id: str, **kw: Any) -> dict[str, Any]:
        proj = self.handler.projection()
        contract = assemble_work_contract(
            proj,
            node_id,
            capabilities=[e.id for e in self.broker.manifest.entries],
            **kw,
        )
        if contract.get("obligation_refs") == ["__none__"]:
            contract["obligation_refs"] = list(proj.nodes[node_id].obligation_refs) or [
                oid for oid, ob in proj.obligations.items() if ob.origin == "root"
            ]
        self._active_contract = contract
        return contract

    def contract_assembled(self, contract: Mapping[str, Any]) -> CommandResult:
        self._active_contract = dict(contract)
        return self.handler.contract_assembled(contract)

    def authorize_maker(self, claim: Mapping[str, Any]) -> CommandResult:
        from eglk_harness.domain.runtime.claim_sanitize import actions_requiring_broker

        contract = self._active_contract or {}
        ceiling = list((contract.get("transaction_policy") or {}).get("side_effect_class_ceiling") or [])
        return self.handler.authorize_actions(
            role="maker",
            actions=actions_requiring_broker(list(claim.get("actions") or [])),
            ceiling=ceiling,
        )

    def dispatch_claim(self, claim: Mapping[str, Any], *, actor: str) -> CommandResult:
        return self.handler.action_dispatched(claim, actor=actor)

    def begin_transaction(self, node_id: str) -> WorldTransaction:
        proj = self.handler.projection()
        contract = self._active_contract or {}
        claim_actions = []
        sec = ceiling_class(claim_actions)
        tx = self.env.begin(
            node_id=node_id,
            base_revision=proj.world_revision,
            side_effect_class=sec,
        )
        tx = self.env.prepare(tx, claim_actions)
        self.handler.transaction_prepared(tx.to_dict())
        self._active_tx = tx
        return tx

    def apply_claim_to_tx(
        self,
        claim: Mapping[str, Any],
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> WorldTransaction:
        from eglk_harness.domain.runtime.claim_sanitize import sanitize_claim_for_apply

        clean = sanitize_claim_for_apply(claim)
        auth = self.authorize_maker(clean)
        if not auth.ok:
            raise PermissionError(auth.error or "capability_denied")

        proj = self.handler.projection()
        contract = self._active_contract or {}
        node_id = str(contract.get("node_id") or claim.get("subgoal_id") or "root")
        sec = ceiling_class(list(clean.get("actions") or []))
        tx = self.env.begin(
            node_id=node_id,
            base_revision=proj.world_revision,
            side_effect_class=sec,
        )
        tx = self.env.prepare(tx, list(clean.get("actions") or []))
        self.handler.transaction_prepared(tx.to_dict())
        resolved = dict(payload) if isinstance(payload, Mapping) else worldref.resolve_claim_payload(clean)
        tx = self.env.apply(tx, claim_payload=resolved)
        world_rev = self.env.observe_revision(tx)
        obs = self.env.observe(tx)
        self.handler.transaction_observed(
            transaction_id=tx.transaction_id,
            world_revision=world_rev,
            observation=obs,
        )
        self._active_tx = tx
        return tx

    def record_evidence(self, evidence: Mapping[str, Any], *, actor: str) -> CommandResult:
        tx = self._active_tx
        if tx is not None:
            ev = dict(evidence)
            ev["world_revision"] = self.env.observe_revision(tx)
            return self.handler.record_evidence(ev, actor=actor)
        return self.handler.record_evidence(evidence, actor=actor)

    def gate_decide(
        self,
        *,
        claim: Mapping[str, Any],
        evidence: Mapping[str, Any],
        is_closure: bool = False,
    ) -> CommandResult:
        contract = self._active_contract or {}
        return self.handler.gate_decide(
            contract=contract,
            claim=claim,
            evidence=evidence,
            is_closure_gate=is_closure,
        )

    def finalize_transaction_after_gate(self, decision: str) -> None:
        tx = self._active_tx
        if tx is None:
            return
        proj = self.handler.projection()
        if decision == "admit":
            self.env.commit(tx)
            self.handler.invalidate_from_commit(
                touches=list(tx.touches),
                transaction_id=tx.transaction_id,
                world_revision=int(tx.candidate_revision or proj.world_revision + 1),
            )
        elif decision in {"repair", "abort"}:
            if tx.side_effect_class == "reversible":
                self.env.rollback(tx, self.workdir)
                self.handler.transaction_rolled_back(tx.transaction_id)
            elif tx.side_effect_class == "compensatable":
                self.env.compensate(tx)
                self.handler.transaction_compensated(tx.transaction_id)
        self._active_tx = None

    def quota(
        self,
        role: str,
        tokens: int,
        usd: float = 0.0,
        *,
        estimation: bool = False,
    ) -> None:
        self.handler.quota_updated(
            role=role,
            tokens_delta=max(1, tokens),
            usd_delta=usd,
            estimation=estimation,
        )

    def root_done(self) -> bool:
        return projection_root_done(self.handler.projection())

    def closure_needed(self) -> bool:
        """True when no ready leaf remains and nothing is mid-tick ``in_progress``.

        Mid-tick ``ContractAssembled`` without Gate leaves ``in_progress``; that must
        NOT count as "ready pool empty → close". Callers should
        ``reopen_stranded_in_progress_nodes()`` at tick start before relying on this.
        """
        proj = self.handler.projection()
        if proj.run_status != "running":
            return False
        if any(n.status == "in_progress" for n in proj.nodes.values()):
            return False
        if select_ready_node(proj) is not None:
            return False
        return True

    def run_closure_gate(self) -> CommandResult:
        from eglk_harness.domain.kernel.closure_evidence import build_closure_verdict

        proj = self.handler.projection()
        root = proj.root_id or "root"
        contract = self.assemble_contract_for_node(root)
        self.contract_assembled(contract)
        events = self.store.read_all()
        verdicts = []
        for oid in contract["obligation_refs"]:
            ob = proj.obligations.get(str(oid))
            if ob is None:
                verdicts.append(
                    {
                        "obligation_id": str(oid),
                        "status": "unsatisfied",
                        "attestations": [],
                        "gaps": ["closure_incomplete"],
                        "defect_suspected": False,
                    }
                )
                continue
            verdicts.append(
                build_closure_verdict(
                    self.workdir,
                    ob,
                    world_revision=int(proj.world_revision),
                    events=events,
                )
            )
        evidence = {
            "schema": "eglk.evidence_bundle",
            "evidence_id": f"eb-closure",
            "contract_ref": contract["contract_id"],
            "checker_session_id": "closure-checker",
            "world_revision": proj.world_revision,
            "verdicts": verdicts,
            "integrity_violation": False,
            "additional_gaps": [],
        }
        claim = {
            "schema": "eglk.action_claim",
            "claim_id": "ac-closure",
            "contract_ref": contract["contract_id"],
            "maker_session_id": "closure-maker",
            "intent": "closure",
            "actions": [],
            "alternatives": [{"text": "none", "status": "reject"}],
            "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
            "world_revision_base": proj.world_revision,
            "node_id": root,
        }
        return self.gate_decide(claim=claim, evidence=evidence, is_closure=True)


def finalize_run_closure(ctx: RunEventContext) -> dict[str, Any]:
    """Run closure Gate when work is complete but ``run_status`` is still ``running``."""
    proj = ctx.handler.projection()
    if not ctx.closure_needed():
        return {"ok": True, "skipped": True, "run_status": proj.run_status}
    res = ctx.run_closure_gate()
    ctx.export_projections()
    proj = ctx.handler.projection()
    closure_payload = res.events[0].payload if res.events else None
    return {
        "ok": res.ok and proj.run_status == "succeeded",
        "run_status": proj.run_status,
        "closure": closure_payload,
    }


def finalize_run_closure_workdir(workdir: Path, goal_id: str) -> dict[str, Any]:
    ctx = RunEventContext(workdir, goal_id)
    ctx.acquire()
    try:
        return finalize_run_closure(ctx)
    finally:
        ctx.release()
