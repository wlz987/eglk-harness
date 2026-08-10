"""verification_matrix §9 — merge must not drop satisfied obligations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.coverage_proof import validate_merge_obligations


def _attestation(observer: str = "c-1") -> dict:
    return {
        "method": "custom_attestation",
        "world_revision": 1,
        "digest": "sha256:" + "d" * 64,
        "observer": observer,
        "raw_ref": "workdir/hello.txt",
        "watch_set": ["workdir/hello.txt"],
    }


def _bootstrap_two_leaf(h: CommandHandler) -> None:
    obligations = [
        {
            "id": "ob-1",
            "requirement_id": "req-1",
            "statement": "hello.txt exists",
            "verification_type": "custom_attestation",
            "status": "open",
            "origin": "root",
        },
        {
            "id": "ob-2",
            "requirement_id": "req-2",
            "statement": "hello.txt exists",
            "verification_type": "custom_attestation",
            "status": "open",
            "origin": "root",
        },
    ]
    h.run_created(
        goal_id="g",
        memory_digest="sha256:" + "a" * 64,
        cognitive_tokens_max=1000,
        repairs_max=8,
    )
    h.goal_compiled(
        {
            "source_digest": "sha256:" + "b" * 64,
            "root_node_id": "root",
            "title": "merge goal",
            "obligation_refs": ["ob-1", "ob-2"],
            "obligations": obligations,
        }
    )
    h.node_ready("root")
    split = h.commit_split(
        {
            "split_node": "root",
            "children": [
                {"id": "root.01", "title": "a", "obligation_refs": ["ob-1"], "depth": 1},
                {"id": "root.02", "title": "b", "obligation_refs": ["ob-2"], "depth": 1},
            ],
            "coverage_proof": {
                "parent_obligation_ids": ["ob-1", "ob-2"],
                "child_obligation_map": {"root.01": ["ob-1"], "root.02": ["ob-2"]},
                "proof_kind": "partition",
            },
        }
    )
    assert split.ok, split.error
    h.node_ready("root.01")
    h.node_ready("root.02")


def _admit_leaf(h: CommandHandler, node_id: str, obligation_id: str) -> None:
    contract = {
        "schema": "eglk.work_contract",
        "contract_id": f"wc-{node_id}",
        "node_id": node_id,
        "obligation_refs": [obligation_id],
        "obligation_verification_types": {obligation_id: "custom_attestation"},
        "boundary": {"allowed_scope": ["workdir/**"], "forbidden_actions": []},
        "transaction_policy": {"side_effect_class_ceiling": ["reversible"]},
    }
    claim = {
        "schema": "eglk.action_claim",
        "claim_id": f"ac-{node_id}",
        "contract_ref": f"wc-{node_id}",
        "maker_session_id": f"m-{node_id}",
        "actions": [],
        "alternatives": [{"text": "x", "status": "reject"}],
    }
    evidence = {
        "schema": "eglk.evidence_bundle",
        "evidence_id": f"ev-{node_id}",
        "contract_ref": f"wc-{node_id}",
        "checker_session_id": f"c-{node_id}",
        "world_revision": 1,
        "verdicts": [
            {
                "obligation_id": obligation_id,
                "status": "satisfied",
                "attestations": [_attestation(f"c-{node_id}")],
                "gaps": [],
                "defect_suspected": False,
            }
        ],
    }
    h.contract_assembled(contract)
    h.action_dispatched(
        {"claim_id": claim["claim_id"], "contract_ref": contract["contract_id"], "maker_session_id": claim["maker_session_id"]},
        actor="maker",
    )
    h.record_evidence(evidence, actor="checker")
    res = h.gate_decide(contract=contract, claim=claim, evidence=evidence)
    assert res.ok, res.error


class TestMergeSatisfiedRegression(unittest.TestCase):
    def test_validate_merge_rejects_dropped_satisfied(self) -> None:
        ok, reason = validate_merge_obligations(
            source_obligation_sets=[["ob-1"], ["ob-2"]],
            merged_obligation_refs=["ob-2"],
            satisfied_obligation_ids=["ob-1"],
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "satisfied_obligation_dropped")

    def test_commit_merge_rejects_dropping_satisfied_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            _bootstrap_two_leaf(h)
            _admit_leaf(h, "root.01", "ob-1")
            proj = h.projection()
            self.assertEqual(proj.obligations["ob-1"].status, "satisfied")
            res = h.commit_merge(
                {
                    "into": "root.m001",
                    "node_ids": ["root.01", "root.02"],
                    "parent_id": "root",
                    "obligation_refs": ["ob-2"],
                    "title": "bad merge",
                }
            )
            self.assertFalse(res.ok)
            self.assertTrue(res.rejected)
            types = [e.type for e in store.read_all()]
            self.assertNotIn("MergeCommitted", types)
            store.release_lease(holder="t")
            store.close()

    def test_merge_retains_satisfied_obligation_status(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            _bootstrap_two_leaf(h)
            _admit_leaf(h, "root.01", "ob-1")
            res = h.commit_merge(
                {
                    "into": "root.m002",
                    "node_ids": ["root.01", "root.02"],
                    "parent_id": "root",
                    "obligation_refs": ["ob-1", "ob-2"],
                    "title": "good merge",
                }
            )
            self.assertTrue(res.ok)
            proj = h.projection()
            self.assertEqual(proj.obligations["ob-1"].status, "satisfied")
            self.assertEqual(proj.obligations["ob-2"].status, "open")
            self.assertIn("MergeCommitted", [e.type for e in store.read_all()])
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
