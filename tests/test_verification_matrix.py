"""Tests aligned with design/kernel/verification_matrix.md."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.coverage_proof import validate_split_coverage
from eglk_harness.domain.kernel.gate import decide
from eglk_harness.domain.kernel.projection_replay import projection_diff, rebuild_from_events
from eglk_harness.domain.kernel.reducer import reduce_events


class TestVerificationMatrix(unittest.TestCase):
    def test_gate_no_eval_imports(self) -> None:
        import ast
        import eglk_harness.domain.kernel.gate as gate_mod

        tree = ast.parse(Path(gate_mod.__file__).read_text(encoding="utf-8"))
        banned = ("eval_runner", "wa_hard", "WebArena")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for b in banned:
                        self.assertNotIn(b, alias.name)
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for b in banned:
                    self.assertNotIn(b, mod)

    def test_split_coverage_partition(self) -> None:
        ok, reason = validate_split_coverage(
            parent_obligation_ids=["ob-1", "ob-2"],
            child_obligation_map={"c1": ["ob-1"], "c2": ["ob-2"]},
            proof_kind="partition",
        )
        self.assertTrue(ok, reason)

    def test_split_coverage_rejects_incomplete(self) -> None:
        ok, reason = validate_split_coverage(
            parent_obligation_ids=["ob-1", "ob-2"],
            child_obligation_map={"c1": ["ob-1"]},
            proof_kind="partition",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "partition_incomplete")

    def test_replay_equivalence_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            loop = Path(td)
            store = EventStore(loop / "events.db")
            store.acquire_lease(holder="t")
            store.append("RunCreated", {"goal_id": "g", "memory_digest": "sha256:" + "a" * 64})
            store.release_lease(holder="t")
            store.close()
            a = rebuild_from_events(loop)
            b = rebuild_from_events(loop)
            self.assertEqual([], projection_diff(a, b))

    def test_commit_split_rejects_without_proof(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
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
                    "title": "t",
                    "obligation_refs": ["ob-1"],
                    "obligations": [
                        {
                            "id": "ob-1",
                            "requirement_id": "req-1",
                            "statement": "s",
                            "verification_type": "custom_attestation",
                            "status": "open",
                            "origin": "root",
                        }
                    ],
                }
            )
            h.node_ready("root")
            bad = h.commit_split(
                {
                    "split_node": "root",
                    "children": [
                        {"id": "root.01", "title": "a", "obligation_refs": [], "depth": 1},
                        {"id": "root.02", "title": "b", "obligation_refs": [], "depth": 1},
                    ],
                    "coverage_proof": {
                        "parent_obligation_ids": ["ob-1"],
                        "child_obligation_map": {},
                        "proof_kind": "partition",
                    },
                }
            )
            self.assertFalse(bad.ok)
            types = [e.type for e in store.read_all()]
            self.assertNotIn("SplitCommitted", types)
            store.release_lease(holder="t")
            store.close()

    def test_maker_not_checker_on_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            h.action_dispatched(
                {"claim_id": "c1", "contract_ref": "wc-1", "maker_session_id": "same"},
                actor="maker",
            )
            res = h.record_evidence(
                {"checker_session_id": "same", "evidence_id": "e1"},
                actor="checker",
            )
            self.assertFalse(res.ok)
            store.release_lease(holder="t")
            store.close()

    def test_commit_merge_creates_into_node(self) -> None:
        obligations = [
            {
                "id": "ob-1",
                "requirement_id": "req-1",
                "statement": "a",
                "verification_type": "custom_attestation",
                "status": "open",
                "origin": "root",
            },
            {
                "id": "ob-2",
                "requirement_id": "req-2",
                "statement": "b",
                "verification_type": "custom_attestation",
                "status": "open",
                "origin": "root",
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
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
                    "title": "t",
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
            self.assertTrue(split.ok)
            merged = h.commit_merge(
                {
                    "into": "root.merged",
                    "node_ids": ["root.01", "root.02"],
                    "parent_id": "root",
                    "title": "merged",
                    "obligation_refs": ["ob-1", "ob-2"],
                }
            )
            self.assertTrue(merged.ok)
            proj = h.projection()
            self.assertIn("root.merged", proj.nodes)
            self.assertEqual(proj.nodes["root.01"].status, "superseded")
            self.assertEqual(proj.nodes["root.02"].status, "superseded")
            self.assertEqual(sorted(proj.nodes["root.merged"].obligation_refs), ["ob-1", "ob-2"])
            types = [e.type for e in store.read_all()]
            self.assertIn("MergeCommitted", types)
            replay = rebuild_from_events(Path(td))
            from eglk_harness.domain.kernel.reducer import run_projection_dict

            state = reduce_events(store.read_all())
            self.assertEqual([], projection_diff(run_projection_dict(state), replay["run"]))
            store.release_lease(holder="t")
            store.close()


class TestGateAbortReasons(unittest.TestCase):
    def test_abort_only_budget(self) -> None:
        contract = {
            "schema": "eglk.work_contract",
            "contract_id": "wc-1",
            "node_id": "n1",
            "obligation_refs": ["ob-1"],
            "transaction_policy": {"side_effect_class_ceiling": ["reversible"]},
        }
        claim = {
            "schema": "eglk.action_claim",
            "claim_id": "ac-1",
            "contract_ref": "wc-1",
            "maker_session_id": "m1",
            "actions": [],
            "alternatives": [{"text": "x", "status": "reject"}],
            "self_assessment": {"done_progress": 0.5, "confidence": 0.5},
        }
        evidence = {
            "schema": "eglk.evidence_bundle",
            "evidence_id": "e1",
            "checker_session_id": "c1",
            "world_revision": 0,
            "verdicts": [
                {
                    "obligation_id": "ob-1",
                    "status": "unsatisfied",
                    "attestations": [],
                    "gaps": ["x"],
                }
            ],
            "integrity_violation": False,
        }
        d = decide(
            contract,
            claim,
            evidence,
            quota={"cognitive_tokens": 99999, "cognitive_tokens_max": 100, "repairs_max": 8},
        )
        self.assertEqual(d.decision, "abort")
        self.assertEqual(d.reason, "cognitive_budget")


if __name__ == "__main__":
    unittest.main()
