"""Gate actor — envelope in/out around ``domain.kernel.gate.decide`` (no LLM)."""

from __future__ import annotations

from typing import Any, Mapping

from eba import Worker

from eglk_harness.domain.kernel.gate import decide
from eglk_harness.domain.kernel.projections import WORK_CONTRACT_SCHEMA
from eglk_harness.protocol import messages, payload, topics


def _obligation_ids_from_evidence(evidence: Mapping[str, Any]) -> list[str]:
    verdicts = evidence.get("verdicts")
    if isinstance(verdicts, list):
        out = [
            str(v.get("obligation_id"))
            for v in verdicts
            if isinstance(v, Mapping) and v.get("obligation_id")
        ]
        if out:
            return out
    return ["ob-1"]


def _work_contract_for_gate(
    claim: Mapping[str, Any],
    evidence: Mapping[str, Any],
    args: Mapping[str, Any],
) -> dict[str, Any]:
    raw = args.get("contract")
    if isinstance(raw, Mapping):
        return dict(raw)
    contract_ref = str(claim.get("contract_ref") or "")
    return {
        "schema": WORK_CONTRACT_SCHEMA,
        "contract_id": contract_ref or f"wc-{claim.get('claim_id', 'gate')}",
        "node_id": str(claim.get("subgoal_id") or claim.get("node_id") or ""),
        "obligation_refs": _obligation_ids_from_evidence(evidence),
        "transaction_policy": {
            "side_effect_class_ceiling": ["read_only", "reversible", "irreversible"],
        },
    }


class GateActor(Worker):
    pattern = f"{topics.GATE_DECIDE}.*"
    result_prefix = topics.GATE_RESULT
    error_code = "gate_failed"

    async def work(self, envelope_payload: Any) -> Any:
        args = payload.get_args(envelope_payload if isinstance(envelope_payload, dict) else {})
        claim = args.get("claim")
        evidence = args.get("evidence")
        if not isinstance(claim, dict) or not isinstance(evidence, dict):
            messages.work_error("missing_claim_or_evidence")
        quota = args.get("quota") if isinstance(args.get("quota"), dict) else {}
        repairs = args.get("repair_counts") if isinstance(args.get("repair_counts"), dict) else {}
        contract = _work_contract_for_gate(claim, evidence, args)
        decision = decide(contract, claim, evidence, quota=quota, repair_counts=repairs)
        return messages.ok_value(decision=decision.to_dict())
