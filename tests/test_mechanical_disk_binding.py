"""Mechanical claim file_write + evidence satisfied path."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.kernel.worldref import apply_claim_actions
from eglk_harness.domain.runtime.mechanical_claim import synthesize_mechanical_claim
from eglk_harness.domain.runtime.mechanical_evidence import synthesize_mechanical_evidence


class MechanicalDiskBindingTests(unittest.TestCase):
    def test_json_deliverable_emits_file_write_and_evidence_satisfies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "agent_runs" / "11").mkdir(parents=True)
            body = {
                "task_type": "RETRIEVE",
                "status": "SUCCESS",
                "retrieved_data": [6],
                "error_details": None,
            }
            (workdir / "agent_runs" / "11" / "agent_response.json").write_text(
                json.dumps(body) + "\n",
                encoding="utf-8",
            )
            (workdir / "agent_runs" / "11" / "network.har").write_text(
                json.dumps({"log": {"version": "1.2", "entries": [{"request": {}}]}}) + "\n",
                encoding="utf-8",
            )
            boundary = [
                "MUST_EXIST: agent_runs/11/agent_response.json",
                "MUST_EXIST: agent_runs/11/network.har",
            ]
            claim = synthesize_mechanical_claim(
                workdir=workdir,
                title="count disappointed reviews",
                subgoal_id="root",
                contract_ref="wc-1",
                world_revision=1,
                obligation_refs=["ob-1", "ob-2"],
                boundary=boundary,
                tick=0,
            )
            self.assertIsNotNone(claim)
            assert claim is not None
            self.assertEqual(claim.get("note"), "mechanical_claim_from_disk")
            kinds = [a.get("kind") for a in claim.get("actions") or []]
            self.assertEqual(kinds.count("file_write"), 1)
            self.assertEqual(kinds.count("path_ack"), 1)
            apply_claim_actions(workdir, claim.get("actions"))
            ev = synthesize_mechanical_evidence(
                workdir=workdir,
                claim=claim,
                contract_ref="wc-1",
                obligation_refs=["ob-1", "ob-2"],
                boundary=boundary,
                world_revision=1,
                tick=0,
            )
            self.assertIsNotNone(ev)
            assert ev is not None
            for v in ev["verdicts"]:
                self.assertEqual(v["status"], "satisfied")
                self.assertTrue(v["attestations"])


if __name__ == "__main__":
    unittest.main()
