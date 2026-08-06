"""Fake Checker worker (M2) — returns Evidence without LLM / tools."""

from __future__ import annotations

from typing import Any

from eba import RequestResponseActor

from eglk_harness.protocol import messages, payload, topics


class FakeCheckerActor(RequestResponseActor):
    pattern = f"{topics.ROLE_CHECKER_RUN}.*"
    result_prefix = topics.ROLE_CHECKER_RESULT
    error_code = "checker_failed"

    def __init__(self, *, mode: str = "admit", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.mode = mode  # admit | repair_integrity | repair_empty

    async def work(self, body: Any) -> Any:
        args = payload.get_args(body if isinstance(body, dict) else {})
        tick = int(args.get("tick", 0))
        claim = args.get("claim") if isinstance(args.get("claim"), dict) else {}
        subgoal_id = str(args.get("subgoal_id") or claim.get("subgoal_id") or "root")
        written = list(args.get("written") or [])

        if self.mode == "repair_integrity":
            evidence = {
                "evidence_id": f"ev-{tick:03d}",
                "tick": tick,
                "checker_session_id": "fake-checker",
                "audit_progress": 1.0,
                "audit_confidence": 0.9,
                "gaps": [],
                "alternatives": [],
                "alternatives_missing": False,
                "challenges": [],
                "cost_usd": 0.0,
                "artifacts": [f"observed:{p}" for p in written] or ["observed:hello.txt"],
                "integrity_violation": True,
                "criteria_defect": False,
                "subgoal_id": subgoal_id,
            }
            return messages.ok_body(evidence=evidence)

        if self.mode == "repair_empty" or not written:
            evidence = {
                "evidence_id": f"ev-{tick:03d}",
                "tick": tick,
                "checker_session_id": "fake-checker",
                "audit_progress": 0.0,
                "audit_confidence": 0.5,
                "gaps": ["no artifacts on disk"],
                "alternatives": [],
                "alternatives_missing": False,
                "challenges": [],
                "cost_usd": 0.0,
                "artifacts": [],
                "integrity_violation": False,
                "criteria_defect": False,
                "subgoal_id": subgoal_id,
            }
            return messages.ok_body(evidence=evidence)

        evidence = {
            "evidence_id": f"ev-{tick:03d}",
            "tick": tick,
            "checker_session_id": "fake-checker",
            "audit_progress": 1.0,
            "audit_confidence": 0.95,
            "gaps": [],
            "alternatives": [],
            "alternatives_missing": False,
            "challenges": [],
            "cost_usd": 0.0,
            "artifacts": [f"observed:{p}" for p in written],
            "integrity_violation": False,
            "criteria_defect": False,
            "subgoal_id": subgoal_id,
        }
        return messages.ok_body(evidence=evidence)
