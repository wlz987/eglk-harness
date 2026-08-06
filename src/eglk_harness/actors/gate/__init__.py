"""Gate actor — envelope in/out around ``domain.gate.decide`` (no LLM)."""

from __future__ import annotations

from typing import Any

from eba import RequestResponseActor

from eglk_harness.domain.gate import decide
from eglk_harness.protocol import messages, payload, topics


class GateActor(RequestResponseActor):
    pattern = f"{topics.GATE_DECIDE}.*"
    result_prefix = topics.GATE_RESULT
    error_code = "gate_failed"

    async def work(self, body: Any) -> Any:
        args = payload.get_args(body if isinstance(body, dict) else {})
        claim = args.get("claim")
        evidence = args.get("evidence")
        if not isinstance(claim, dict) or not isinstance(evidence, dict):
            return messages.err_body("missing_claim_or_evidence")
        quota = args.get("quota") if isinstance(args.get("quota"), dict) else {}
        repairs = args.get("repair_counts") if isinstance(args.get("repair_counts"), dict) else {}
        decision = decide(claim, evidence, quota=quota, repair_counts=repairs)
        return messages.ok_body(decision=decision.to_dict())
