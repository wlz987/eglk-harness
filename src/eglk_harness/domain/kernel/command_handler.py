"""CommandHandler — sole EventStore write path; validates commands → events."""

from __future__ import annotations

import os
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
        ev = self.store.append(type_, payload, actor=kw.get("actor"), causation_id=kw.get("causation_id"), correlation_id=kw.get("correlation_id"))
        # incremental: rebuild for correctness (small logs)
        self._projection = reduce_events(self.store.read_all())
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
        # Maker≠Checker: compare against last ActionDispatched if present
        for ev in reversed(self.store.read_all()):
            if ev.type == "ActionDispatched":
                maker_sid = (ev.payload or {}).get("maker_session_id")
                break
        checker_sid = evidence.get("checker_session_id")
        if maker_sid and checker_sid and str(maker_sid) == str(checker_sid):
            return CommandResult(
                ok=False,
                events=[],
                error="maker_equals_checker",
                rejected=True,
            )
        ev = self._append("EvidenceRecorded", {"evidence": dict(evidence)}, actor=actor)
        return CommandResult(ok=True, events=[ev])

    def action_dispatched(self, claim: Mapping[str, Any], *, actor: str) -> CommandResult:
        ev = self._append(
            "ActionDispatched",
            {
                "claim_id": claim.get("claim_id"),
                "contract_ref": claim.get("contract_ref"),
                "maker_session_id": claim.get("maker_session_id"),
                "actions": claim.get("actions") or [],
                "claim": dict(claim),
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
            closure_complete=coverage_complete(proj) if is_closure_gate else None,
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
            if ob.status == "satisfied" and set(ob.watch_set) & touch_set:
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

    def export_projections(self) -> dict[str, Any]:
        proj = self.projection(force_rebuild=True)
        return {
            "run": run_projection_dict(proj),
            "task_structure": task_structure_dict(proj),
            "repair_counts": dict(proj.repair_counts),
            "last_gate": proj.last_gate,
        }

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
