"""Claim disk rebind when LLM file_write payload is a schema template."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.runtime.mechanical_claim import (
    claim_file_writes_match_disk,
    prefer_disk_bound_claim,
    rebind_claim_from_disk,
)


class ClaimDiskRebindTests(unittest.TestCase):
    def test_rebind_replaces_template_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            rel = "agent_runs/11/agent_response.json"
            disk = {
                "task_type": "RETRIEVE",
                "status": "SUCCESS",
                "retrieved_data": [6],
                "error_details": None,
            }
            (workdir / rel).parent.mkdir(parents=True, exist_ok=True)
            (workdir / rel).write_text(json.dumps(disk) + "\n", encoding="utf-8")
            boundary = [f"MUST_EXIST: {rel}"]
            claim = {
                "schema": "eglk.action_claim",
                "actions": [
                    {
                        "action_id": "a1",
                        "kind": "file_write",
                        "side_effect_class": "reversible",
                        "target": rel,
                        "payload": {
                            "description": "official",
                            "shape": "{\"retrieved_data\":[<count>]}",
                        },
                    }
                ],
            }
            rebound = rebind_claim_from_disk(claim, workdir, boundary)
            self.assertTrue(claim_file_writes_match_disk(rebound, workdir, boundary))
            self.assertEqual(rebound["actions"][0]["payload"], disk)

    def test_prefer_disk_bound_over_template_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            rel = "out/answer.json"
            disk = {"ok": True, "value": 42}
            (workdir / rel).parent.mkdir(parents=True, exist_ok=True)
            (workdir / rel).write_text(json.dumps(disk) + "\n", encoding="utf-8")
            boundary = [f"MUST_EXIST: {rel}"]
            llm_claim = {
                "actions": [
                    {
                        "kind": "file_write",
                        "target": rel,
                        "payload": {"ok": False},
                    }
                ],
            }
            final = prefer_disk_bound_claim(
                llm_claim,
                workdir=workdir,
                boundary=boundary,
                title="t",
                subgoal_id="root",
                contract_ref="wc-1",
                world_revision=0,
                obligation_refs=["ob-1"],
                tick=0,
            )
            self.assertIsNotNone(final)
            assert final is not None
            self.assertTrue(claim_file_writes_match_disk(final, workdir, boundary))


if __name__ == "__main__":
    unittest.main()
