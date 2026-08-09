"""CommandHandler — sole EventStore write path; validates commands → events."""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Mapping

from eglk_harness.domain.capability import CapabilityBroker
from eglk_harness.domain.event_store import EventEnvelope, EventStore, HashChainBroken
from eglk_harness.domain.kernel import gate as gate_mod
from eglk_harness.domain.kernel.reducer import (
    ProjectionState,
    reduce_events,
    run_projection_dict,
    task_structure_dict,
)
from eglk_harness.domain.kernel.scheduler import coverage_complete
from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.coverage_proof import validate_merge_obligations, validate_split_coverage
from eglk_harness.domain.kernel.covers import covers_closure_complete, covers_edges_from_refinement
from eglk_harness.domain.kernel.session_policy import (
    assign_checker_session,
    assign_maker_session,
    validate_checker_session,
    validate_maker_session,
)
from eglk_harness.domain.kernel.reducer import obligation_ledger_dict


@dataclass
class CommandResult:
    ok: bool
    events: list[EventEnvelope]
    error: str | None = None
    rejected: bool = False


class CommandHandler:
    """Validate role/mechanical commands and append events. Only writer of events.db."""

    def __init__(
        self,
        store: EventStore,
        *,
        holder: str | None = None,
        broker: CapabilityBroker | None = None,
    ) -> None:
        self.store = store
        self.holder = holder or f"pid-{os.getpid()}"
        self.broker = broker
        self._projection: ProjectionState | None = None

    def acquire(self) -> None:
        self.store.acquire_lease(holder=self.holder)

    def release(self) -> None:
        self.store.release_lease(holder=self.holder)

    def projection(self, *, force_rebuild: bool = False) -> ProjectionState:
        if self._projection is None or force_rebuild:
            self._projection = reduce_events(self.store.read_all())
        return self._projection

    def _append(self, type_: str, payload: Mapping[str, Any], **kw: Any) -> EventEnvelope:
        from eglk_harness.domain.kernel.reducer import apply_event, reduce_events

        ev = self.store.append(
            type_,
            payload,
            actor=kw.get("actor"),
            causation_id=kw.get("causation_id"),
            correlation_id=kw.get("correlation_id"),
        )
        if self._projection is None:
            self._projection = reduce_events(self.store.read_all())
        else:
            apply_event(self._projection, ev)
        return ev

    def verify_or_fault(self) -> CommandResult:
        try:
            self.store.verify_hash_chain()
            return CommandResult(ok=True, events=[])
        except HashChainBroken as exc:
            ev = self._append("RunFaulted", {"reason": "hash_chain_broken", "detail": str(exc)})
            return CommandResult(ok=False, events=[ev], error=str(exc))

    def run_created(
        self,
        *,
        goal_id: str,
        memory_digest: str,
        capability_manifest_ref: str | None = None,
        cognitive_tokens_max: int,
        repairs_max: int,
    ) -> CommandResult:
        ev = self._append(
            "RunCreated",
            {
                "goal_id": goal_id,
                "memory_digest": memory_digest,
                "capability_manifest_ref": capability_manifest_ref,
                "cognitive_tokens_max": cognitive_tokens_max,
                "repairs_max": repairs_max,
            },
        )
        return CommandResult(ok=True, events=[ev])

    def goal_compiled(self, payload: Mapping[str, Any]) -> CommandResult:
        digest = str(payload.get("source_digest") or "")
        for ev in self.store.read_all():
            if ev.type != "GoalCompiled":
                continue
            prior = str((ev.payload or {}).get("source_digest") or "")
            if prior and digest and prior != digest:
                return self.run_invalid(
                    "goal_drift",
                    detail=f"expected={prior} actual={digest}",
                )
            break
        ev = self._append("GoalCompiled", payload)
        return CommandResult(ok=True, events=[ev])

    def node_ready(self, node_id: str) -> CommandResult:
        ev = self._append("NodeReady", {"node_id": node_id})
        return CommandResult(ok=True, events=[ev])

    def contract_assembled(self, contract: Mapping[str, Any]) -> CommandResult:
        # schema-level required fields must exist
        required = (
            "contract_id",
            "node_id",
            "obligation_refs",
            "boundary",
            "transaction_policy",
        )
        for k in required:
            if k not in contract:
                return CommandResult(ok=False, events=[], error=f"missing {k}", rejected=True)
        ev = self._append(
            "ContractAssembled",
            {
                "contract_id": contract["contract_id"],
                "node_id": contract["node_id"],
                "contract": dict(contract),
            },
        )
        return CommandResult(ok=True, events=[ev])

    def authorize_actions(
        self,
        *,
        role: str,
        actions: list[Mapping[str, Any]],
        ceiling: list[str],
    ) -> CommandResult:
        if self.broker is None:
            return CommandResult(ok=True, events=[])
        events: list[EventEnvelope] = []
        for action in actions:
            decision = self.broker.authorize_action(role=role, action=action, ceiling=ceiling)
            if not decision.allowed:
                ev = self._append(
                    "CapabilityDenied",
                    {
                        "action_id": action.get("action_id"),
                        "role": role,
                        "reason": decision.reason,
                        "requested_side_effect_class": action.get("side_effect_class"),
                        "entry_id": decision.entry_id,
                    },
                )
                events.append(ev)
                return CommandResult(ok=False, events=events, error=decision.reason, rejected=True)
        return CommandResult(ok=True, events=events)

    def record_evidence(self, evidence: Mapping[str, Any], *, actor: str) -> CommandResult:
        maker_sid = None
        contract_ref = str(evidence.get("contract_ref") or "")
        for ev in reversed(self.store.read_all()):
            if ev.type == "ActionDispatched":
                p = ev.payload or {}
                maker_sid = p.get("maker_session_id")
                if not contract_ref:
                    contract_ref = str(p.get("contract_ref") or "")
                break
        ev_doc = dict(evidence)
        raw_checker = str(ev_doc.get("checker_session_id") or "").strip()
        if maker_sid and raw_checker and raw_checker == str(maker_sid):
            return CommandResult(
                ok=False,
                events=[],
                error="maker_equals_checker",
                rejected=True,
            )
        if contract_ref:
            assign_checker_session(
                ev_doc,
                contract_ref,
                maker_session_id=str(maker_sid or ""),
            )
        ok, reason = validate_checker_session(
            ev_doc,
            maker_session_id=str(maker_sid or "") if maker_sid else None,
            events=self.store.read_all(),
        )
        if not ok:
            return CommandResult(ok=False, events=[], error=reason, rejected=True)
        ev = self._append("EvidenceRecorded", {"evidence": ev_doc}, actor=actor)
        return CommandResult(ok=True, events=[ev])

    def action_dispatched(self, claim: Mapping[str, Any], *, actor: str) -> CommandResult:
        claim_doc = dict(claim)
        contract_ref = str(claim_doc.get("contract_ref") or "")
        if contract_ref:
            assign_maker_session(claim_doc, contract_ref)
        ok, reason = validate_maker_session(claim_doc, self.store.read_all())
        if not ok:
            return self.reject_command(command="action_dispatched", reason=reason, actor=actor)
        ev = self._append(
            "ActionDispatched",
            {
                "claim_id": claim_doc.get("claim_id"),
                "contract_ref": claim_doc.get("contract_ref"),
                "maker_session_id": claim_doc.get("maker_session_id"),
                "actions": claim_doc.get("actions") or [],
                "claim": claim_doc,
            },
            actor=actor,
        )
        return CommandResult(ok=True, events=[ev])

    def gate_decide(
        self,
        *,
        contract: Mapping[str, Any],
        claim: Mapping[str, Any],
        evidence: Mapping[str, Any],
        is_closure_gate: bool = False,
    ) -> CommandResult:
        proj = self.projection()
        decision = gate_mod.decide(
            contract,
            claim,
            evidence,
            quota={
                "cognitive_tokens": proj.cognitive_tokens,
                "cognitive_tokens_max": proj.cognitive_tokens_max,
                "repairs_max": proj.repairs_max,
            },
            repair_counts=proj.repair_counts,
            pending_amendment_obligation_ids=list(proj.pending_amendments),
            is_closure_gate=is_closure_gate,
            closure_complete=covers_closure_complete(proj) if is_closure_gate else None,
        )
        events: list[EventEnvelope] = []
        gd = decision.to_dict()
        ev = self._append("GateDecided", gd)
        events.append(ev)
        gd["event_ref"] = ev.event_id

        if decision.decision == "admit":
            for oid in decision.satisfied_obligation_ids:
                watch: list[str] = []
                for v in evidence.get("verdicts") or []:
                    if isinstance(v, Mapping) and str(v.get("obligation_id")) == oid:
                        for a in v.get("attestations") or []:
                            if isinstance(a, Mapping):
                                watch.extend(str(x) for x in (a.get("watch_set") or []))
                events.append(
                    self._append(
                        "ObligationSatisfied",
                        {
                            "obligation_id": oid,
                            "watch_set": watch,
                            "world_revision": evidence.get("world_revision"),
                            "causation_gate": ev.event_id,
                        },
                        causation_id=ev.event_id,
                    )
                )
            if is_closure_gate and decision.reason == "closure_admitted":
                events.append(
                    self._append(
                        "RunSucceeded",
                        {"reason": "closure_admitted", "gate_event_id": ev.event_id},
                        causation_id=ev.event_id,
                    )
                )
        elif decision.decision == "abort":
            events.append(
                self._append(
                    "RunAborted",
                    {"reason": decision.reason, "gate_event_id": ev.event_id},
                    causation_id=ev.event_id,
                )
            )
        return CommandResult(ok=True, events=events)

    def invalidate_from_commit(self, *, touches: list[str], transaction_id: str, world_revision: int) -> CommandResult:
        events: list[EventEnvelope] = []
        events.append(
            self._append(
                "TransactionCommitted",
                {
                    "transaction_id": transaction_id,
                    "touches": touches,
                    "world_revision": world_revision,
                },
            )
        )
        proj = self.projection()
        touch_set = set(touches)
        for oid, ob in proj.obligations.items():
            if ob.status != "satisfied" or not (set(ob.watch_set) & touch_set):
                continue
            # Obligations proven at this revision (or later) are not stale yet.
            if ob.world_revision is not None and int(ob.world_revision) >= int(world_revision):
                continue
            events.append(
                self._append(
                    "ObligationInvalidated",
                    {
                        "obligation_id": oid,
                        "cause_transaction_id": transaction_id,
                    },
                )
            )
        return CommandResult(ok=True, events=events)

    def quota_updated(
        self,
        *,
        role: str,
        tokens_delta: int,
        estimation: bool = False,
        usd_delta: float = 0.0,
    ) -> CommandResult:
        if tokens_delta <= 0 and not estimation:
            # Invariant 8: never record zero for a real call; require conservative estimate
            tokens_delta = 1
        proj = self.projection()
        by_role = dict(proj.cognitive_tokens_by_role)
        by_role[role] = int(by_role.get(role, 0)) + int(tokens_delta)
        total = sum(by_role.values())
        ev = self._append(
            "QuotaUpdated",
            {
                "cognitive_tokens": total,
                "cognitive_tokens_by_role": by_role,
                "usd_used": float(proj.usd_used) + float(usd_delta),
                "repairs_used": proj.repairs_used,
                "estimation": estimation,
                "role": role,
                "tokens_delta": tokens_delta,
            },
        )
        return CommandResult(ok=True, events=[ev])

    def memory_candidate_written(
        self,
        record: Mapping[str, Any],
        *,
        actor: str = "maker",
    ) -> CommandResult:
        ev = self._append(
            "MemoryCandidateWritten",
            {"record": dict(record), "record_id": record.get("id")},
            actor=actor,
        )
        return CommandResult(ok=True, events=[ev])

    def memory_promoted(
        self,
        *,
        record_id: str,
        from_status: str,
        to_status: str,
        actor: str = "refiner",
    ) -> CommandResult:
        ev = self._append(
            "MemoryPromoted",
            {
                "record_id": record_id,
                "from_status": from_status,
                "to_status": to_status,
            },
            actor=actor,
        )
        return CommandResult(ok=True, events=[ev])

    def memory_deprecated(
        self,
        *,
        record_id: str,
        from_status: str,
        reason: str = "ttl_expired",
        actor: str = "refiner",
    ) -> CommandResult:
        ev = self._append(
            "MemoryDeprecated",
            {
                "record_id": record_id,
                "from_status": from_status,
                "reason": reason,
            },
            actor=actor,
        )
        return CommandResult(ok=True, events=[ev])

    def export_projections(self) -> dict[str, Any]:
        proj = self.projection(force_rebuild=True)
        return {
            "run": run_projection_dict(proj),
            "task_structure": task_structure_dict(proj),
            "obligation_ledger": obligation_ledger_dict(proj),
            "repair_counts": dict(proj.repair_counts),
            "last_gate": proj.last_gate,
        }

    def reject_command(
        self,
        *,
        command: str,
        reason: str,
        actor: str = "command_handler",
        detail: str | None = None,
    ) -> CommandResult:
        ev = self._append(
            "CommandRejected",
            {"command": command, "reason": reason, "detail": detail or ""},
            actor=actor,
        )
        return CommandResult(ok=False, events=[ev], error=reason, rejected=True)

    def check_goal_drift(self, workdir: Path) -> CommandResult:
        from eglk_harness.domain.kernel import paths as kpaths
        from eglk_harness.domain.kernel.run_engine import _goal_digest

        proj = self.projection()
        goal_path = kpaths.goal_path(workdir)
        if not goal_path.is_file():
            return CommandResult(ok=True, events=[])
        digest = _goal_digest(goal_path.read_text(encoding="utf-8"))
        if proj.goal_spec_ref and proj.last_sequence >= 0:
            # compare against GoalCompiled payload in log
            for ev in self.store.read_all():
                if ev.type == "GoalCompiled":
                    compiled = str((ev.payload or {}).get("source_digest") or "")
                    if compiled and compiled != digest:
                        inv = self._append(
                            "RunInvalid",
                            {"reason": "goal_drift", "expected": compiled, "actual": digest},
                        )
                        return CommandResult(ok=False, events=[inv], error="goal_drift")
                    break
        return CommandResult(ok=True, events=[])

    def run_invalid(self, reason: str, *, detail: str | None = None) -> CommandResult:
        ev = self._append("RunInvalid", {"reason": reason, "detail": detail or ""})
        return CommandResult(ok=False, events=[ev], error=reason)

    def run_faulted(self, reason: str, *, detail: str | None = None) -> CommandResult:
        ev = self._append("RunFaulted", {"reason": reason, "detail": detail or ""})
        return CommandResult(ok=False, events=[ev], error=reason)

    def run_recovery_started(self, reason: str = "crash_recovery") -> CommandResult:
        ev = self._append("RunRecoveryStarted", {"reason": reason})
        return CommandResult(ok=True, events=[ev])

    def run_recovery_completed(self, run_status: str = "running") -> CommandResult:
        ev = self._append("RunRecoveryCompleted", {"run_status": run_status})
        return CommandResult(ok=True, events=[ev])

    def transaction_prepared(self, tx: Mapping[str, Any]) -> CommandResult:
        ev = self._append("TransactionPrepared", dict(tx))
        return CommandResult(ok=True, events=[ev])

    def transaction_observed(
        self,
        *,
        transaction_id: str,
        world_revision: int,
        observation: Mapping[str, Any] | None = None,
    ) -> CommandResult:
        ev = self._append(
            "TransactionObserved",
            {
                "transaction_id": transaction_id,
                "world_revision": world_revision,
                "observation": dict(observation or {}),
            },
        )
        return CommandResult(ok=True, events=[ev])

    def transaction_rolled_back(self, transaction_id: str) -> CommandResult:
        ev = self._append("TransactionRolledBack", {"transaction_id": transaction_id})
        return CommandResult(ok=True, events=[ev])

    def transaction_compensated(self, transaction_id: str) -> CommandResult:
        ev = self._append("TransactionCompensated", {"transaction_id": transaction_id})
        return CommandResult(ok=True, events=[ev])

    def commit_split(
        self,
        payload: Mapping[str, Any],
        *,
        actor: str = "governor",
    ) -> CommandResult:
        """Validate CoverageProof and append SplitCommitted + opened obligations."""
        proj = self.projection()
        node_id = str(payload.get("split_node") or payload.get("node_id") or "")
        node = proj.nodes.get(node_id)
        if node is None:
            return self.reject_command(command="split", reason="unknown_node", actor=actor)
        depth = node.depth
        if depth >= P.MAX_SPLIT_DEPTH:
            return self.reject_command(command="split", reason="max_split_depth", actor=actor)

        proof = payload.get("coverage_proof") or {}
        parent_obs = [str(x) for x in (proof.get("parent_obligation_ids") or node.obligation_refs or [])]
        child_map_raw = proof.get("child_obligation_map") or {}
        child_map: dict[str, list[str]] = {}
        if isinstance(child_map_raw, Mapping):
            for k, v in child_map_raw.items():
                child_map[str(k)] = [str(x) for x in (v or [])]

        opened = [dict(x) for x in (payload.get("opened_obligations") or []) if isinstance(x, Mapping)]
        proof_kind = str(proof.get("proof_kind") or "partition")
        ok, reason = validate_split_coverage(
            parent_obligation_ids=parent_obs,
            child_obligation_map=child_map,
            proof_kind=proof_kind,
            opened_obligations=opened,
        )
        if not ok:
            return self.reject_command(command="split", reason=reason, actor=actor)

        children = [dict(c) for c in (payload.get("children") or []) if isinstance(c, Mapping)]
        if not (P.SPLIT_CHILDREN_MIN <= len(children) <= P.SPLIT_CHILDREN_MAX):
            return self.reject_command(command="split", reason="children_count", actor=actor)

        events: list[EventEnvelope] = []
        for ob in opened:
            oid = str(ob.get("id") or "")
            if not oid:
                continue
            events.append(
                self._append(
                    "ObligationOpened",
                    {
                        "obligation_id": oid,
                        "requirement_id": ob.get("requirement_id"),
                        "parent_obligation_id": ob.get("parent_obligation_id"),
                        "statement": ob.get("statement"),
                        "verification_type": ob.get("verification_type"),
                        "origin": ob.get("origin") or "derived",
                    },
                    actor=actor,
                )
            )

        obligation_covers = covers_edges_from_refinement(opened)
        depends_on = [dict(x) for x in (payload.get("depends_on") or []) if isinstance(x, Mapping)]

        split_ev = self._append(
            "SplitCommitted",
            {
                "node_id": node_id,
                "coverage_proof_ref": proof.get("ref") or None,
                "coverage_proof": dict(proof),
                "children": children,
                "opened_obligation_ids": [str(o.get("id")) for o in opened if o.get("id")],
                "obligation_covers": obligation_covers,
                "depends_on": depends_on,
            },
            actor=actor,
        )
        events.append(split_ev)

        for child in children:
            cid = str(child.get("id") or "")
            if cid:
                events.append(self._append("NodeReady", {"node_id": cid}, actor=actor))

        return CommandResult(ok=True, events=events)

    def commit_merge(
        self,
        payload: Mapping[str, Any],
        *,
        actor: str = "governor",
    ) -> CommandResult:
        proj = self.projection()
        into = str(payload.get("into") or "")
        source_ids = [str(x) for x in (payload.get("node_ids") or payload.get("nodes") or [])]
        merged_refs = [str(x) for x in (payload.get("obligation_refs") or [])]
        if not into or not source_ids:
            return self.reject_command(command="merge", reason="missing_into_or_sources", actor=actor)

        source_sets: list[list[str]] = []
        satisfied: list[str] = []
        for sid in source_ids:
            n = proj.nodes.get(sid)
            if n is None:
                return self.reject_command(command="merge", reason=f"unknown_node:{sid}", actor=actor)
            source_sets.append(list(n.obligation_refs))
            for oid in n.obligation_refs:
                ob = proj.obligations.get(oid)
                if ob and ob.status == "satisfied":
                    satisfied.append(oid)

        if not merged_refs:
            union: list[str] = []
            seen: set[str] = set()
            for refs in source_sets:
                for oid in refs:
                    if oid not in seen:
                        seen.add(oid)
                        union.append(oid)
            merged_refs = union

        ok, reason = validate_merge_obligations(
            source_obligation_sets=source_sets,
            merged_obligation_refs=merged_refs,
            satisfied_obligation_ids=satisfied,
        )
        if not ok:
            return self.reject_command(command="merge", reason=reason, actor=actor)

        ev = self._append(
            "MergeCommitted",
            {
                "into": into,
                "node_ids": source_ids,
                "obligation_refs": merged_refs,
                "parent_id": payload.get("parent_id"),
                "title": payload.get("title"),
            },
            actor=actor,
        )
        self._append("NodeReady", {"node_id": into}, actor=actor)
        return CommandResult(ok=True, events=[ev])

    def propose_obligation_amendment(
        self,
        *,
        obligation_id: str,
        new_statement: str,
        new_verification_type: str | None = None,
        coverage_proof: Mapping[str, Any] | None = None,
        actor: str = "governor",
    ) -> CommandResult:
        """Propose Amendment for derived obligations only (root → rejected)."""
        proj = self.projection()
        ob = proj.obligations.get(obligation_id)
        if ob is None:
            return CommandResult(ok=False, events=[], error="unknown_obligation", rejected=True)
        if ob.origin == "root" or ob.parent_obligation_id is None:
            ev = self._append(
                "ObligationAmendmentRejected",
                {
                    "obligation_id": obligation_id,
                    "reason": "root_obligation_immutable",
                },
                actor=actor,
            )
            return CommandResult(ok=False, events=[ev], error="root_obligation_immutable", rejected=True)
        old_statement = ob.statement
        proposed = self._append(
            "ObligationAmendmentProposed",
            {
                "obligation_id": obligation_id,
                "old_statement": old_statement,
                "new_statement": new_statement,
                "new_verification_type": new_verification_type or ob.verification_type,
                "coverage_proof": dict(coverage_proof or {"kind": "refinement", "parent": ob.parent_obligation_id}),
            },
            actor=actor,
        )
        # Mechanical coverage: new statement must be non-empty and parent must still exist
        parent_id = str(ob.parent_obligation_id)
        if not new_statement.strip() or parent_id not in proj.obligations:
            rej = self._append(
                "ObligationAmendmentRejected",
                {"obligation_id": obligation_id, "reason": "coverage_proof_failed"},
                actor=actor,
                causation_id=proposed.event_id,
            )
            return CommandResult(ok=False, events=[proposed, rej], error="coverage_proof_failed", rejected=True)
        accepted = self._append(
            "ObligationAmended",
            {
                "obligation_id": obligation_id,
                "old_statement": old_statement,
                "new_statement": new_statement.strip(),
                "new_verification_type": new_verification_type or ob.verification_type,
                "parent_obligation_id": parent_id,
            },
            actor=actor,
            causation_id=proposed.event_id,
        )
        return CommandResult(ok=True, events=[proposed, accepted])

    def record_defect_suspected_amendments(
        self,
        evidence: Mapping[str, Any],
        *,
        actor: str = "governor",
    ) -> list[CommandResult]:
        """If Checker marks defect_suspected on derived obligations, propose conservative amendments."""
        results: list[CommandResult] = []
        proj = self.projection()
        for v in evidence.get("verdicts") or []:
            if not isinstance(v, Mapping):
                continue
            if v.get("defect_suspected") is not True:
                continue
            oid = str(v.get("obligation_id") or "")
            ob = proj.obligations.get(oid)
            if ob is None or ob.origin == "root":
                continue
            gaps = v.get("gaps") or []
            note = "; ".join(str(g) for g in gaps[:3]) if gaps else "statement refinement"
            new_stmt = f"{ob.statement} [refined: {note}]".strip()
            results.append(
                self.propose_obligation_amendment(
                    obligation_id=oid,
                    new_statement=new_stmt,
                    new_verification_type="custom_attestation",
                    actor=actor,
                )
            )
        return results
