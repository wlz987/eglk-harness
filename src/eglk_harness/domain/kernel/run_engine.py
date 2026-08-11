"""Event-driven run engine — optional tick path; production uses TickRunLoop + CommandHandler."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.capability import CapabilityBroker, ensure_manifest
from eglk_harness.domain.event_store import open_store
from eglk_harness.domain.environment.world_transaction import (
    LocalFilesystemAdapter,
    ceiling_class,
)
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.projections import (
    effective_cognitive_tokens_max,
    effective_repairs_max,
)
from eglk_harness.domain.kernel.goal_parse import INTENT_CRITERIA_FALLBACK, intent_criteria
from eglk_harness.domain.kernel.obligation_compile import compile_root_obligations
from eglk_harness.domain.kernel.covers import covers_closure_complete
from eglk_harness.domain.kernel.scheduler import (
    assemble_work_contract,
    select_ready_node,
    should_propose_split,
)
from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.memory.lifecycle import digest_active_snapshot
from eglk_harness.domain.kernel.schema_validate import coerce_document, validate_document


def _goal_digest(goal_text: str) -> str:
    return "sha256:" + hashlib.sha256(goal_text.encode("utf-8")).hexdigest()


def compile_goal_spec(
    workdir: Path,
    *,
    goal_id: str,
    goal_text: str,
    done_criteria: list[str] | None = None,
) -> dict[str, Any]:
    """Mechanical GoalSpec frame — coarse root obligations (conservative verification_type)."""
    criteria = list(done_criteria or [])
    if not criteria and goal_text.strip():
        criteria = intent_criteria(goal_text)
    if not criteria:
        criteria = [INTENT_CRITERIA_FALLBACK]
    obligations = compile_root_obligations(criteria, requirement_id="req-1", id_prefix="ob")
    spec = {
        "schema": P.GOAL_SPEC_SCHEMA,
        "goal_id": goal_id,
        "source_digest": _goal_digest(goal_text),
        "compiled_at": __import__("datetime")
        .datetime.now(__import__("datetime").timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "compiler_mode": "auto",
        "requirements": [
            {
                "id": "req-1",
                "text": goal_text.strip().splitlines()[0][:500] if goal_text.strip() else "goal",
                "source_span": {"start_line": 1, "end_line": max(1, len(goal_text.splitlines()))},
                "obligations": obligations,
            }
        ],
        "quota_defaults": {
            "cognitive_tokens_max": effective_cognitive_tokens_max(),
            "repairs_max": effective_repairs_max(),
            "usd_soft": None,
        },
    }
    return spec


class RunEngine:
    """Minimal event-driven main chain: Scheduler → Maker → Env → Checker → Gate."""

    def __init__(
        self,
        workdir: Path,
        *,
        goal_id: str,
        goal_title: str = "goal",
        done_criteria: list[str] | None = None,
        swarm_soft: str | None = None,
    ) -> None:
        self.workdir = Path(workdir).resolve()
        self.goal_id = goal_id
        self.goal_title = goal_title
        self.done_criteria = list(done_criteria or [])
        self.swarm_soft = swarm_soft
        self.loop_dir = paths.ensure_loop_layout(self.workdir, goal_id)
        paths.ensure_memory_layout(self.workdir)
        self.store = open_store(self.loop_dir)
        manifest = ensure_manifest(paths.capability_manifest_path(self.workdir))
        self.broker = CapabilityBroker(manifest)
        self.handler = CommandHandler(self.store, broker=self.broker)
        self.env = LocalFilesystemAdapter(self.workdir, self.loop_dir / "world")
        self.outcome: dict[str, Any] | None = None

    @staticmethod
    def tick_job_factory() -> type:
        """EBA Job adapter — mechanical orchestration over RunEventContext."""
        from eglk_harness.actors.tick import TickJob

        return TickJob

    def bootstrap(self) -> None:
        self.handler.acquire()
        try:
            from eglk_harness.domain.kernel.recovery import reconcile_dangling_transactions

            reconcile_dangling_transactions(
                self.handler, workdir=self.workdir, env=self.env
            )
            self.handler.check_goal_drift(self.workdir)
            self.handler.verify_or_fault()
            proj = self.handler.projection()
            if proj.run_status in {"succeeded", "aborted", "invalid", "faulted"}:
                return
            if proj.last_sequence < 0 or proj.run_status == "created":
                goal_path = paths.goal_path(self.workdir)
                goal_text = goal_path.read_text(encoding="utf-8") if goal_path.is_file() else self.goal_title
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
                    done_criteria=self.done_criteria or None,
                )
                # persist goal_spec projection
                (paths.projections_dir(self.workdir, self.goal_id) / "goal_spec.json").write_text(
                    json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                ob_ids = [o["id"] for o in spec["requirements"][0]["obligations"]]
                self.handler.goal_compiled(
                    {
                        "goal_spec_ref": "projections/goal_spec.json",
                        "source_digest": spec["source_digest"],
                        "root_node_id": "root",
                        "title": self.goal_title,
                        "obligation_refs": ob_ids,
                        "obligations": spec["requirements"][0]["obligations"],
                    }
                )
                # root starts ready when no deps
                self.handler.node_ready("root")
                # mark root node obligation_refs on projection via GoalCompiled already
        finally:
            self.export()

    def export(self) -> None:
        proj_dir = paths.projections_dir(self.workdir, self.goal_id)
        exported = self.handler.export_projections()
        (proj_dir / "run_projection.json").write_text(
            json.dumps(exported["run"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if exported.get("task_structure"):
            (proj_dir / "task_structure.json").write_text(
                json.dumps(exported["task_structure"], indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    def step_with_artifacts(
        self,
        *,
        claim: Mapping[str, Any],
        evidence: Mapping[str, Any],
        tokens_maker: int = 100,
        tokens_checker: int = 80,
    ) -> dict[str, Any]:
        """Drive one contract cycle given already-produced claim/evidence (tests / mock)."""
        self.handler.acquire()
        try:
            proj = self.handler.projection()
            if proj.run_status in {"succeeded", "aborted", "invalid", "faulted"}:
                return {"run_status": proj.run_status, "stopped": True}

            node_id = select_ready_node(proj)
            if node_id is None:
                if covers_closure_complete(proj):
                    # closure gate with synthetic empty claim/evidence for root
                    root = proj.root_id or "root"
                    contract = assemble_work_contract(
                        proj,
                        root,
                        capabilities=[e.id for e in self.broker.manifest.entries],
                    )
                    # Ensure root obligations reflected
                    if not contract["obligation_refs"] or contract["obligation_refs"] == ["__none__"]:
                        contract["obligation_refs"] = [
                            oid for oid, ob in proj.obligations.items() if ob.origin == "root"
                        ] or list(proj.obligations.keys())
                    self.handler.contract_assembled(contract)
                    # Build satisfied evidence for closure
                    verdicts = []
                    for oid in contract["obligation_refs"]:
                        ob = proj.obligations.get(oid)
                        if ob and ob.status == "satisfied":
                            verdicts.append(
                                {
                                    "obligation_id": oid,
                                    "status": "satisfied",
                                    "attestations": [
                                        {
                                            "method": ob.verification_type,
                                            "world_revision": proj.world_revision,
                                            "digest": f"closure:{oid}",
                                            "observer": "closure",
                                            "raw_ref": f"closure/{oid}",
                                            "watch_set": list(ob.watch_set),
                                        }
                                    ],
                                    "gaps": [],
                                    "defect_suspected": False,
                                }
                            )
                        else:
                            verdicts.append(
                                {
                                    "obligation_id": oid,
                                    "status": "unsatisfied",
                                    "attestations": [],
                                    "gaps": ["closure_incomplete"],
                                    "defect_suspected": False,
                                }
                            )
                    eb = {
                        "schema": P.EVIDENCE_BUNDLE_SCHEMA,
                        "evidence_id": f"eb-closure-{uuid.uuid4().hex[:8]}",
                        "contract_ref": contract["contract_id"],
                        "checker_session_id": "closure-checker",
                        "world_revision": proj.world_revision,
                        "verdicts": verdicts,
                        "integrity_violation": False,
                        "additional_gaps": [],
                    }
                    ac = {
                        "schema": P.ACTION_CLAIM_SCHEMA,
                        "claim_id": f"ac-closure-{uuid.uuid4().hex[:8]}",
                        "contract_ref": contract["contract_id"],
                        "maker_session_id": "closure-maker",
                        "intent": "root closure",
                        "actions": [],
                        "alternatives": [{"text": "none", "status": "reject"}],
                        "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
                        "world_revision_base": proj.world_revision,
                    }
                    result = self.handler.gate_decide(
                        contract=contract, claim=ac, evidence=eb, is_closure_gate=True
                    )
                    self.export()
                    return {"closure": True, "events": [e.type for e in result.events]}

                return {"waiting_deps": True}

            contract = assemble_work_contract(
                proj,
                node_id,
                capabilities=[e.id for e in self.broker.manifest.entries],
            )
            if contract["obligation_refs"] == ["__none__"]:
                contract["obligation_refs"] = list(proj.nodes[node_id].obligation_refs) or list(
                    proj.obligations.keys()
                )
            self.handler.contract_assembled(contract)

            claim_doc = coerce_document("action_claim", dict(claim))
            claim_doc["contract_ref"] = contract["contract_id"]
            claim_doc["world_revision_base"] = contract["world_revision_base"]
            # Align verdicts to contract obligations
            ev_doc = coerce_document("evidence_bundle", dict(evidence))
            ev_doc["contract_ref"] = contract["contract_id"]
            from eglk_harness.domain.runtime.contract_align import align_evidence_to_contract

            ev_doc = align_evidence_to_contract(
                ev_doc,
                contract_ref=str(contract["contract_id"]),
                obligation_refs=list(contract["obligation_refs"]),
                world_revision=int(ev_doc.get("world_revision") or 0),
            )

            errs = validate_document("action_claim", claim_doc)
            if errs:
                return {"error": "claim_schema", "detail": errs}
            errs = validate_document("evidence_bundle", ev_doc)
            if errs:
                return {"error": "evidence_schema", "detail": errs}

            ceiling = list(contract["transaction_policy"]["side_effect_class_ceiling"])
            auth = self.handler.authorize_actions(
                role="maker", actions=list(claim_doc.get("actions") or []), ceiling=ceiling
            )
            if not auth.ok:
                # still run gate so capability_ceiling becomes repair
                claim_doc.setdefault("actions", [])
                # inject illegal action marker via ceiling check inside gate
                pass

            self.handler.action_dispatched(claim_doc, actor=str(claim_doc.get("maker_session_id")))
            self.handler.quota_updated(role="maker", tokens_delta=max(1, tokens_maker))

            sec = ceiling_class(list(claim_doc.get("actions") or []))
            tx = self.env.begin(
                node_id=node_id, base_revision=proj.world_revision, side_effect_class=sec
            )
            tx = self.env.prepare(tx, list(claim_doc.get("actions") or []))
            from eglk_harness.domain.kernel.worldref import resolve_claim_payload

            tx = self.env.apply(tx, claim_payload=resolve_claim_payload(claim_doc))
            world_rev = self.env.observe_revision(tx)
            ev_doc["world_revision"] = world_rev

            rec = self.handler.record_evidence(ev_doc, actor=str(ev_doc.get("checker_session_id")))
            if not rec.ok:
                return {"error": rec.error, "rejected": True}
            self.handler.quota_updated(role="checker", tokens_delta=max(1, tokens_checker))

            gd = self.handler.gate_decide(contract=contract, claim=claim_doc, evidence=ev_doc)
            decision = (gd.events[0].payload if gd.events else {})
            dec = str(decision.get("decision") or "")
            if dec == "admit":
                self.env.commit(tx)
                self.handler.invalidate_from_commit(
                    touches=list(tx.touches),
                    transaction_id=tx.transaction_id,
                    world_revision=int(tx.candidate_revision or proj.world_revision + 1),
                )
            elif dec in {"repair", "abort"} and tx.side_effect_class == "reversible":
                self.env.rollback(tx, self.workdir)
                self.handler.transaction_rolled_back(tx.transaction_id)
            elif dec in {"repair", "abort"} and tx.side_effect_class == "compensatable":
                self.env.compensate(tx)
                self.handler.transaction_compensated(tx.transaction_id)

            # split proposal hint (Governor is advisor — recorded in outcome only here)
            proj2 = self.handler.projection()
            split_hint = should_propose_split(proj2, node_id, P.SPLIT_REPAIR_STREAK)

            self.export()
            return {
                "node_id": node_id,
                "decision": decision,
                "split_hint": split_hint,
                "run_status": proj2.run_status,
                "transaction": tx.to_dict(),
            }
        finally:
            self.handler.release()

    def close(self) -> None:
        try:
            self.handler.release()
        finally:
            self.store.close()
