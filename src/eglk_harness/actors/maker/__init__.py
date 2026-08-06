"""Fake Maker worker (M2) — returns a grounded files Claim without LLM."""

from __future__ import annotations

from typing import Any

from eba import RequestResponseActor

from eglk_harness.protocol import messages, payload, topics


class FakeMakerActor(RequestResponseActor):
    """Echo a successful files claim that writes ``hello.txt``."""

    pattern = f"{topics.ROLE_MAKER_RUN}.*"
    result_prefix = topics.ROLE_MAKER_RESULT
    error_code = "maker_failed"

    def __init__(self, *, mode: str = "admit", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.mode = mode  # admit | repair_integrity | repair_empty

    async def work(self, body: Any) -> Any:
        args = payload.get_args(body if isinstance(body, dict) else {})
        tick = int(args.get("tick", 0))
        subgoal_id = str(args.get("subgoal_id") or "root")

        if self.mode == "repair_empty":
            claim = {
                "claim_id": f"claim-{tick:03d}",
                "tick": tick,
                "maker_session_id": "fake-maker",
                "kind": "files",
                "done_progress": 1.0,
                "confidence": 0.9,
                "alternatives": [{"text": "noop", "status": "reject", "reason": "worse"}],
                "payload": {"files": {}},
                "shortcut_hit": False,
                "subgoal_id": subgoal_id,
            }
            return messages.ok_body(claim=claim)

        content = "hello from fake maker\n"
        if self.mode == "repair_integrity":
            content = "tampered\n"

        claim = {
            "claim_id": f"claim-{tick:03d}",
            "tick": tick,
            "maker_session_id": "fake-maker",
            "kind": "files",
            "done_progress": 1.0,
            "confidence": 0.95,
            "alternatives": [
                {"text": "leave file unchanged", "status": "reject", "reason": "incomplete"},
            ],
            "payload": {"files": {"hello.txt": content}},
            "shortcut_hit": False,
            "subgoal_id": subgoal_id,
        }
        return messages.ok_body(claim=claim)
