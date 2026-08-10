"""Task structure graph: depends_on promotion and obligation invalidation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.advisors import build_mechanical_split_candidate
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.projection_view import split_depends_on_chain
from eglk_harness.domain.kernel.scheduler import deps_satisfied, select_ready_node


class TestDependsOnChain(unittest.TestCase):
    def test_split_depends_on_chain_order(self) -> None:
        edges = split_depends_on_chain(["a", "b", "c"])
        self.assertEqual(
            edges,
            [
                {"from": "b", "to": "a", "kind": "depends_on"},
                {"from": "c", "to": "b", "kind": "depends_on"},
            ],
        )

    def test_refinement_split_only_first_child_ready(self) -> None:
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
                    "title": "one criterion",
                    "obligation_refs": ["ob-1"],
                    "obligations": [
                        {
                            "id": "ob-1",
                            "requirement_id": "req-1",
                            "statement": "deliver hello.txt",
                            "verification_type": "custom_attestation",
                            "status": "open",
                            "origin": "root",
                        }
                    ],
                }
            )
            h.node_ready("root")
            proj = h.projection()
            mech = build_mechanical_split_candidate(proj, "root", step=0)
            self.assertIsNotNone(mech)
            self.assertGreaterEqual(len(mech.get("depends_on") or []), 1)
            res = h.commit_split(mech, actor="governor")
            self.assertTrue(res.ok, res.error)
            proj = h.projection()
            child_ids = [c["id"] for c in mech["children"]]
            self.assertEqual(proj.nodes[child_ids[0]].status, "ready")
            self.assertEqual(proj.nodes[child_ids[1]].status, "pending")
            self.assertFalse(deps_satisfied(proj, child_ids[1]))
            self.assertEqual(select_ready_node(proj), child_ids[0])
            store.release_lease(holder="t")
            store.close()

    def test_admit_promotes_dependent_child(self) -> None:
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
                    "title": "one criterion",
                    "obligation_refs": ["ob-1"],
                    "obligations": [
                        {
                            "id": "ob-1",
                            "requirement_id": "req-1",
                            "statement": "deliver hello.txt",
                            "verification_type": "custom_attestation",
                            "status": "open",
                            "origin": "root",
                        }
                    ],
                }
            )
            h.node_ready("root")
            mech = build_mechanical_split_candidate(h.projection(), "root", step=0)
            h.commit_split(mech, actor="governor")
            proj = h.projection()
            first = mech["children"][0]["id"]
            second = mech["children"][1]["id"]
            contract = {
                "schema": "eglk.work_contract",
                "contract_id": "wc-1",
                "node_id": first,
                "obligation_refs": proj.nodes[first].obligation_refs,
                "boundary": {"allowed_scope": ["workdir/**"], "forbidden_actions": []},
                "capabilities": [],
                "transaction_policy": {"side_effect_class_ceiling": ["read_only", "reversible"]},
                "budget": {"cognitive_tokens_soft": 1000},
                "world_revision_base": 0,
            }
            h.contract_assembled(contract)
            claim = {
                "schema": "eglk.action_claim",
                "claim_id": "ac-1",
                "contract_ref": "wc-1",
                "maker_session_id": "m-1",
                "node_id": first,
                "actions": [],
                "alternatives": [{"text": "x", "status": "reject"}],
                "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
            }
            evidence = {
                "schema": "eglk.evidence_bundle",
                "evidence_id": "e-1",
                "contract_ref": "wc-1",
                "checker_session_id": "c-1",
                "world_revision": 1,
                "verdicts": [
                    {
                        "obligation_id": proj.nodes[first].obligation_refs[0],
                        "status": "satisfied",
                        "attestations": [
                            {
                                "method": "custom_attestation",
                                "world_revision": 1,
                                "digest": "sha256:" + "d" * 64,
                                "observer": "c-1",
                                "raw_ref": "workdir/hello.txt",
                                "watch_set": ["workdir/hello.txt"],
                            }
                        ],
                        "gaps": [],
                    }
                ],
            }
            h.gate_decide(contract=contract, claim=claim, evidence=evidence)
            proj = h.projection()
            self.assertEqual(proj.nodes[first].status, "admitted")
            self.assertEqual(proj.nodes[second].status, "ready")
            store.release_lease(holder="t")
            store.close()


class TestObligationInvalidated(unittest.TestCase):
    def test_stale_watch_set_invalidates_on_new_revision(self) -> None:
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
                            "statement": "hello.txt exists",
                            "verification_type": "custom_attestation",
                            "status": "open",
                            "origin": "root",
                        }
                    ],
                }
            )
            h.node_ready("root")
            contract = {
                "schema": "eglk.work_contract",
                "contract_id": "wc-1",
                "node_id": "root",
                "obligation_refs": ["ob-1"],
                "boundary": {"allowed_scope": ["workdir/**"], "forbidden_actions": []},
                "capabilities": [],
                "transaction_policy": {"side_effect_class_ceiling": ["read_only", "reversible"]},
                "budget": {"cognitive_tokens_soft": 1000},
                "world_revision_base": 0,
            }
            claim = {
                "schema": "eglk.action_claim",
                "claim_id": "ac-1",
                "contract_ref": "wc-1",
                "maker_session_id": "m-1",
                "node_id": "root",
                "actions": [],
                "alternatives": [{"text": "x", "status": "reject"}],
                "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
            }
            evidence = {
                "schema": "eglk.evidence_bundle",
                "evidence_id": "e-1",
                "contract_ref": "wc-1",
                "checker_session_id": "c-1",
                "world_revision": 1,
                "verdicts": [
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
                                "watch_set": ["workdir/hello.txt"],
                            }
                        ],
                        "gaps": [],
                    }
                ],
            }
            h.gate_decide(contract=contract, claim=claim, evidence=evidence)
            self.assertEqual(h.projection().obligations["ob-1"].status, "satisfied")
            h.invalidate_from_commit(
                touches=["workdir/hello.txt"],
                transaction_id="tx-2",
                world_revision=2,
            )
            types = [e.type for e in store.read_all()]
            self.assertIn("ObligationInvalidated", types)
            self.assertEqual(h.projection().obligations["ob-1"].status, "invalidated")
            store.release_lease(holder="t")
            store.close()
