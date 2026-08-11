"""Closure evidence rebind — semantic watch_set must not break closure."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.kernel.closure_evidence import (
    build_closure_verdict,
    is_path_like_watch_entry,
    path_like_watch_entries,
)
from eglk_harness.domain.kernel.reducer import ObligationState


class TestClosureEvidence(unittest.TestCase):
    def test_semantic_watch_not_path(self) -> None:
        self.assertFalse(is_path_like_watch_entry("task_type:RETRIEVE"))
        self.assertTrue(is_path_like_watch_entry("agent_runs/11/agent_response.json"))
        entries = path_like_watch_entries(
            ["task_type:RETRIEVE", "agent_runs/11/agent_response.json"]
        )
        self.assertEqual(entries, ["agent_runs/11/agent_response.json"])

    def test_closure_rebinds_from_prior_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            rel = "agent_runs/11/agent_response.json"
            path = workdir / rel
            path.parent.mkdir(parents=True)
            path.write_text('{"retrieved_data":[6]}\n', encoding="utf-8")
            ob = ObligationState(
                id="ob-1",
                statement="intent",
                verification_type="custom_attestation",
                status="satisfied",
                watch_set=[
                    "task_type:RETRIEVE",
                    "enumeration_exhausted:true",
                ],
            )
            class _Ev:
                type = "EvidenceRecorded"
                payload = {
                    "evidence": {
                        "verdicts": [
                            {
                                "obligation_id": "ob-1",
                                "status": "satisfied",
                                "attestations": [
                                    {
                                        "method": "custom_attestation",
                                        "world_revision": 1,
                                        "digest": "sha256:dead",
                                        "observer": "checker-1",
                                        "raw_ref": rel,
                                        "watch_set": [rel],
                                    }
                                ],
                            }
                        ]
                    }
                }

            verdict = build_closure_verdict(
                workdir,
                ob,
                world_revision=2,
                events=[_Ev()],
            )
            self.assertEqual(verdict["status"], "satisfied")
            self.assertTrue(verdict["attestations"])
            self.assertEqual(verdict["attestations"][0]["world_revision"], 2)
            self.assertTrue(
                str(verdict["attestations"][0]["digest"]).startswith("sha256:")
            )
            self.assertNotEqual(verdict["attestations"][0]["digest"], "sha256:dead")

    def test_closure_semantic_only_without_prior_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            ob = ObligationState(
                id="ob-1",
                statement="intent",
                verification_type="custom_attestation",
                status="satisfied",
                watch_set=["task_type:RETRIEVE"],
            )
            verdict = build_closure_verdict(workdir, ob, world_revision=0, events=[])
            self.assertEqual(verdict["status"], "unsatisfied")
            self.assertIn("closure:missing_rebind_attestation", verdict["gaps"])


if __name__ == "__main__":
    unittest.main()
