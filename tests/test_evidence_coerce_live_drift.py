"""Evidence coerce must accept live-model drift (gap objects, string revisions)."""

from __future__ import annotations

import json
import unittest

from eglk_harness.domain.kernel.schema_validate import coerce_document, parse_and_validate, validate_document


class EvidenceCoerceLiveDriftTests(unittest.TestCase):
    def test_gap_objects_and_string_world_revision(self) -> None:
        raw = {
            "schema": "eglk.evidence_bundle",
            "evidence_id": "eb-1",
            "contract_ref": "wc-1",
            "checker_session_id": "checker-1",
            "world_revision": "0",
            "verdicts": [
                {
                    "obligation_id": "ob-1",
                    "status": "unsatisfied",
                    "attestations": [
                        {
                            "method": "file_exists",
                            "world_revision": "0",
                            "digest": "sha256:abc",
                            "observer": "checker",
                            "raw_ref": "agent_runs/11/agent_response.json",
                            "watch_set": ["agent_runs/11/agent_response.json"],
                        }
                    ],
                    "gaps": [
                        {"gap": "retrieved_data is placeholder"},
                        {"text": "session redirected to login"},
                    ],
                    "defect_suspected": False,
                }
            ],
            "integrity_violation": False,
            "additional_gaps": [{"gap": "boundary:placeholder answer"}],
        }
        doc = coerce_document("evidence", raw)
        errs = validate_document("evidence", doc)
        self.assertEqual(errs, [])
        self.assertEqual(doc["world_revision"], 0)
        self.assertEqual(doc["verdicts"][0]["gaps"][0], "retrieved_data is placeholder")
        self.assertEqual(doc["verdicts"][0]["attestations"][0]["world_revision"], 0)
        self.assertEqual(doc["additional_gaps"][0], "boundary:placeholder answer")

    def test_parse_and_validate_live_shape(self) -> None:
        text = json.dumps(
            {
                "schema": "eglk.evidence_bundle",
                "evidence_id": "eb-2",
                "contract_ref": "wc-2",
                "checker_session_id": "c2",
                "world_revision": "1",
                "verdicts": [
                    {
                        "obligation_id": "ob-1",
                        "status": "satisfied",
                        "attestations": [
                            {
                                "method": "file_exists",
                                "world_revision": "1",
                                "digest": "d",
                                "observer": "c2",
                                "raw_ref": "hello.txt",
                                "watch_set": ["hello.txt"],
                            }
                        ],
                        "gaps": [],
                        "defect_suspected": False,
                    }
                ],
                "integrity_violation": False,
                "additional_gaps": [],
            }
        )
        doc, errs = parse_and_validate("evidence", text)
        self.assertIsNotNone(doc)
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
