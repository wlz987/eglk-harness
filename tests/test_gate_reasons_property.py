"""Gate reason paths — property coverage for verification_matrix §4."""

from __future__ import annotations

import unittest

from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.gate import decide, ABORT_REASONS


def _base_contract(**kw: object) -> dict:
    return {
        "schema": "eglk.work_contract",
        "contract_id": "wc-1",
        "node_id": "leaf",
        "obligation_refs": ["ob-1"],
        "transaction_policy": {"side_effect_class_ceiling": ["read_only", "reversible"]},
        **kw,
    }


def _base_claim(**kw: object) -> dict:
    return {
        "schema": "eglk.action_claim",
        "claim_id": "ac-1",
        "contract_ref": "wc-1",
        "maker_session_id": "m-1",
        "actions": [],
        "alternatives": [{"text": "alt", "status": "reject"}],
        **kw,
    }


def _base_evidence(**kw: object) -> dict:
    return {
        "schema": "eglk.evidence_bundle",
        "evidence_id": "ev-1",
        "contract_ref": "wc-1",
        "checker_session_id": "c-1",
        "world_revision": 1,
        "verdicts": [
            {
                "obligation_id": "ob-1",
                "status": "unsatisfied",
                "attestations": [],
                "gaps": [],
                "defect_suspected": False,
            }
        ],
        **kw,
    }


class TestGateReasonProperties(unittest.TestCase):
    def test_missing_alternatives_repair(self) -> None:
        d = decide(
            _base_contract(),
            _base_claim(alternatives=[]),
            _base_evidence(),
        )
        self.assertEqual(d.decision, "repair")
        self.assertEqual(d.reason, "missing_alternatives")

    def test_capability_ceiling_exceeded_repair(self) -> None:
        d = decide(
            _base_contract(transaction_policy={"side_effect_class_ceiling": ["read_only"]}),
            _base_claim(
                actions=[
                    {
                        "action_id": "a1",
                        "kind": "file_write",
                        "side_effect_class": "reversible",
                    }
                ]
            ),
            _base_evidence(),
        )
        self.assertEqual(d.decision, "repair")
        self.assertEqual(d.reason, "capability_ceiling_exceeded")

    def test_boundary_unmet_repair(self) -> None:
        d = decide(
            _base_contract(),
            _base_claim(),
            _base_evidence(additional_gaps=["boundary:forbidden_path"]),
        )
        self.assertEqual(d.decision, "repair")
        self.assertEqual(d.reason, "boundary_unmet")

    def test_amendment_pending_repair(self) -> None:
        d = decide(
            _base_contract(),
            _base_claim(),
            _base_evidence(),
            pending_amendment_obligation_ids=["ob-1"],
        )
        self.assertEqual(d.decision, "repair")
        self.assertEqual(d.reason, "amendment_pending")

    def test_closure_gate_admitted_when_complete(self) -> None:
        d = decide(
            _base_contract(
                obligation_verification_types={"ob-1": "custom_attestation"},
            ),
            _base_claim(),
            _base_evidence(
                verdicts=[
                    {
                        "obligation_id": "ob-1",
                        "status": "satisfied",
                        "attestations": [
                            {
                                "method": "custom_attestation",
                                "world_revision": 1,
                                "digest": "sha256:" + "d" * 64,
                                "observer": "c-1",
                                "raw_ref": "workdir/hello.txt",
                            }
                        ],
                        "gaps": [],
                        "defect_suspected": False,
                    }
                ]
            ),
            is_closure_gate=True,
            closure_complete=True,
        )
        self.assertEqual(d.decision, "admit")
        self.assertEqual(d.reason, "closure_admitted")
        self.assertTrue(d.is_closure_gate)

    def test_closure_incomplete_repair(self) -> None:
        d = decide(
            _base_contract(),
            _base_claim(),
            _base_evidence(),
            is_closure_gate=True,
            closure_complete=False,
        )
        self.assertEqual(d.decision, "repair")
        self.assertEqual(d.reason, "closure_incomplete")

    def test_repair_exhaustion_abort_reason_in_schema(self) -> None:
        from eglk_harness.domain.kernel.repair_counts import repair_count_key

        key = repair_count_key("__all__", "missing_alternatives")
        d = decide(
            _base_contract(),
            _base_claim(alternatives=[]),
            _base_evidence(),
            quota={"repairs_max": 8},
            repair_counts={key: 8},
        )
        self.assertEqual(d.decision, "abort")
        self.assertIn(d.reason, ABORT_REASONS)
        self.assertTrue(d.reason.endswith("_exhausted"))


if __name__ == "__main__":
    unittest.main()
