"""Contract alignment — Checker verdict ids must match WorkContract for Gate admit."""

from __future__ import annotations

import unittest

from eglk_harness.domain.kernel.gate import decide
from eglk_harness.domain.runtime.contract_align import (
    align_claim_to_contract,
    align_evidence_to_contract,
    PLACEHOLDER_OBLIGATION_ID,
)


class ContractAlignTests(unittest.TestCase):
    def test_align_evidence_maps_ob_unknown_to_contract_obligation(self) -> None:
        evidence = {
            "schema": "eglk.evidence_bundle",
            "evidence_id": "e-1",
            "contract_ref": "wc-unknown",
            "checker_session_id": "chk-1",
            "world_revision": 0,
            "integrity_violation": False,
            "additional_gaps": [],
            "verdicts": [
                {
                    "obligation_id": PLACEHOLDER_OBLIGATION_ID,
                    "status": "satisfied",
                    "attestations": [
                        {
                            "method": "custom_attestation",
                            "world_revision": 0,
                            "digest": "agent_runs/44/agent_response.json",
                            "observer": "chk-1",
                            "raw_ref": "agent_runs/44/agent_response.json",
                            "watch_set": [],
                        }
                    ],
                    "gaps": [],
                    "defect_suspected": False,
                }
            ],
        }
        aligned = align_evidence_to_contract(
            evidence,
            contract_ref="wc-2a458d98d643",
            obligation_refs=["ob-1.01.01.01"],
            world_revision=0,
        )
        self.assertEqual(aligned["contract_ref"], "wc-2a458d98d643")
        self.assertEqual(len(aligned["verdicts"]), 1)
        self.assertEqual(aligned["verdicts"][0]["obligation_id"], "ob-1.01.01.01")
        self.assertEqual(aligned["verdicts"][0]["status"], "satisfied")

    def test_gate_admits_after_alignment(self) -> None:
        contract = {
            "contract_id": "wc-test",
            "node_id": "root.01",
            "obligation_refs": ["ob-leaf-1"],
            "obligation_verification_types": {"ob-leaf-1": "custom_attestation"},
            "transaction_policy": {"side_effect_class_ceiling": ["read_only", "reversible"]},
        }
        claim = align_claim_to_contract(
            {
                "schema": "eglk.action_claim",
                "claim_id": "c-1",
                "contract_ref": "wc-unknown",
                "maker_session_id": "m-1",
                "intent": "deliver",
                "actions": [],
                "alternatives": [{"text": "skip", "status": "reject"}],
                "self_assessment": {"done_progress": 1.0, "confidence": 0.9},
                "world_revision_base": 0,
            },
            contract_ref="wc-test",
            obligation_refs=["ob-leaf-1"],
        )
        evidence = align_evidence_to_contract(
            {
                "schema": "eglk.evidence_bundle",
                "evidence_id": "e-1",
                "contract_ref": "wc-unknown",
                "checker_session_id": "c-1",
                "world_revision": 0,
                "integrity_violation": False,
                "additional_gaps": [],
                "verdicts": [
                    {
                        "obligation_id": PLACEHOLDER_OBLIGATION_ID,
                        "status": "satisfied",
                        "attestations": [
                            {
                                "method": "custom_attestation",
                                "world_revision": 0,
                                "digest": "hello.txt",
                                "observer": "c-1",
                                "raw_ref": "hello.txt",
                                "watch_set": [],
                            }
                        ],
                        "gaps": [],
                        "defect_suspected": False,
                    }
                ],
            },
            contract_ref="wc-test",
            obligation_refs=["ob-leaf-1"],
            world_revision=0,
        )
        decision = decide(contract, claim, evidence, quota={"repairs_max": 8})
        self.assertEqual(decision.decision, "admit")
        self.assertEqual(decision.satisfied_obligation_ids, ["ob-leaf-1"])

    def test_multi_obligation_verdicts_per_ref(self) -> None:
        evidence = align_evidence_to_contract(
            {
                "schema": "eglk.evidence_bundle",
                "evidence_id": "e-2",
                "contract_ref": "wc-x",
                "checker_session_id": "c-2",
                "world_revision": 1,
                "integrity_violation": False,
                "additional_gaps": [],
                "verdicts": [
                    {
                        "obligation_id": PLACEHOLDER_OBLIGATION_ID,
                        "status": "satisfied",
                        "attestations": [
                            {
                                "method": "file_exists",
                                "world_revision": 1,
                                "digest": "a.txt",
                                "observer": "c-2",
                                "raw_ref": "a.txt",
                                "watch_set": ["a.txt"],
                            }
                        ],
                        "gaps": [],
                        "defect_suspected": False,
                    }
                ],
            },
            contract_ref="wc-x",
            obligation_refs=["ob-a", "ob-b"],
            world_revision=1,
        )
        ids = {v["obligation_id"] for v in evidence["verdicts"]}
        self.assertEqual(ids, {"ob-a", "ob-b"})


if __name__ == "__main__":
    unittest.main()
