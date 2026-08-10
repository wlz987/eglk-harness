"""Claim recovery from visible.txt / agent_message."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.runtime.claim_recovery import recover_claim_from_episode


class ClaimRecoveryTests(unittest.TestCase):
    def test_recovers_from_visible_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            tee = d / "maker_000_claim.jsonl"
            tee.write_text("{}", encoding="utf-8")
            claim = {
                "schema": "eglk.action_claim",
                "claim_id": "c1",
                "contract_ref": "wc-1",
                "maker_session_id": "m1",
                "intent": "test",
                "actions": [],
                "alternatives": [{"text": "x", "status": "reject", "reason": "not needed"}],
                "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
                "world_revision_base": 0,
            }
            vis = d / "maker_000_claim.visible.txt"
            vis.write_text(json.dumps(claim) + "\n", encoding="utf-8")
            out = recover_claim_from_episode(str(tee))
            self.assertIsNotNone(out)
            assert out is not None
            self.assertEqual(out.get("claim_id"), "c1")


if __name__ == "__main__":
    unittest.main()
