"""Unit tests for eglk-harness core (EventStore, Gate, Capability, RunEngine)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.capability import CapabilityBroker, default_local_fs_manifest
from eglk_harness.domain.event_store import EventStore, HashChainBroken, open_store
from eglk_harness.domain.kernel.gate import decide
from eglk_harness.domain.kernel.projections import INVARIANT_COUNT
from eglk_harness.domain.kernel.run_engine import RunEngine
from eglk_harness.domain.kernel.schema_validate import coerce_document, validate_document
from eglk_harness.domain.memory.lifecycle import digest_active_snapshot, write_candidate
from eglk_harness.domain.product.check_projections import check_projections
from eglk_harness.domain.product.init_project import init_project

class TestProjectionsPin(unittest.TestCase):
    def test_check_projections(self) -> None:
        report = check_projections()
        self.assertTrue(report.ok, msg=json.dumps(report.to_dict(), indent=2))
        self.assertEqual(INVARIANT_COUNT, 12)

class TestEventStore(unittest.TestCase):
    def test_hash_chain_and_cas(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t1")
            e0 = store.append("RunCreated", {"goal_id": "g1", "memory_digest": "sha256:" + "a" * 64})
            self.assertEqual(e0.sequence, 0)
            self.assertIsNone(e0.prev_hash)
            e1 = store.append("GoalCompiled", {"goal_spec_ref": "x", "source_digest": "sha256:" + "b" * 64})
            self.assertEqual(e1.sequence, 1)
            self.assertEqual(e1.prev_hash, e0.hash)
            store.verify_hash_chain()
            with self.assertRaises(Exception):
                store.append("NodeReady", {"node_id": "n"}, expected_sequence=99)
            store.release_lease(holder="t1")
            store.close()

class TestGate(unittest.TestCase):
    def _contract(self) -> dict:
        return {
            "schema": "eglk.work_contract",
            "contract_id": "wc-1",
            "node_id": "n-1",
            "world_revision_base": 0,
            "obligation_refs": ["ob-1"],
            "dependencies": [],
            "boundary": {"allowed_scope": ["workdir/**"], "forbidden_actions": []},
            "capabilities": [],
            "transaction_policy": {"side_effect_class_ceiling": ["reversible"]},
            "budget": {"cognitive_tokens_soft": 100},
            "prior_evidence_refs": [],
        }

    def _claim(self, **kw) -> dict:
        base = {
            "schema": "eglk.action_claim",
            "claim_id": "ac-1",
            "contract_ref": "wc-1",
            "maker_session_id": "m1",
            "intent": "write",
            "actions": [
                {
                    "action_id": "a1",
                    "kind": "file_write",
                    "side_effect_class": "reversible",
                    "target": "workdir/hello.txt",
                }
            ],
            "alternatives": [{"text": "skip", "status": "reject"}],
            "self_assessment": {"done_progress": 0.9, "confidence": 0.8},
            "world_revision_base": 0,
        }
        base.update(kw)
        return base

    def _evidence(self, *, satisfied: bool = True, integrity: bool = False) -> dict:
        atts = []
        if satisfied:
            atts = [
                {
                    "method": "file_exists",
                    "world_revision": 1,
                    "digest": "sha256:" + "c" * 64,
                    "observer": "c1",
                    "raw_ref": "workdir/hello.txt",
                    "watch_set": ["workdir/hello.txt"],
                }
            ]
        return {
            "schema": "eglk.evidence_bundle",
            "evidence_id": "eb-1",
            "contract_ref": "wc-1",
            "checker_session_id": "c1",
            "world_revision": 1,
            "verdicts": [
                {
                    "obligation_id": "ob-1",
                    "status": "satisfied" if satisfied else "unsatisfied",
                    "attestations": atts,
                    "gaps": [] if satisfied else ["missing"],
                    "defect_suspected": False,
                }
            ],
            "integrity_violation": integrity,
            "additional_gaps": [],
        }

    def test_admit_obligations_satisfied(self) -> None:
        d = decide(self._contract(), self._claim(), self._evidence(satisfied=True))
        self.assertEqual(d.decision, "admit")
        self.assertEqual(d.reason, "obligations_satisfied")

    def test_no_self_assessment_authority(self) -> None:
        # Even with done_progress=1, unsatisfied evidence must repair
        claim = self._claim()
        claim["self_assessment"] = {"done_progress": 1.0, "confidence": 1.0}
        d = decide(self._contract(), claim, self._evidence(satisfied=False))
        self.assertEqual(d.decision, "repair")

    def test_integrity_violation(self) -> None:
        d = decide(self._contract(), self._claim(), self._evidence(satisfied=True, integrity=True))
        self.assertEqual(d.decision, "repair")
        self.assertEqual(d.reason, "integrity_violation")

    def test_cognitive_budget_abort(self) -> None:
        d = decide(
            self._contract(),
            self._claim(),
            self._evidence(satisfied=True),
            quota={"cognitive_tokens": 64000, "cognitive_tokens_max": 64000, "repairs_max": 8},
        )
        self.assertEqual(d.decision, "abort")
        self.assertEqual(d.reason, "cognitive_budget")

    def test_repairs_exhausted(self) -> None:
        d = decide(
            self._contract(),
            self._claim(),
            self._evidence(satisfied=True, integrity=True),
            quota={"cognitive_tokens": 0, "cognitive_tokens_max": 64000, "repairs_max": 8},
            repair_counts={"integrity_violation": 8},
        )
        self.assertEqual(d.decision, "abort")
        self.assertTrue(d.reason.endswith("_exhausted"))

    def test_ceiling_exceeded(self) -> None:
        claim = self._claim()
        claim["actions"] = [
            {
                "action_id": "a1",
                "kind": "http_call",
                "side_effect_class": "irreversible",
                "target": "api/x",
                "idempotency_key": "k1",
            }
        ]
        d = decide(self._contract(), claim, self._evidence(satisfied=False))
        self.assertEqual(d.decision, "repair")
        self.assertEqual(d.reason, "capability_ceiling_exceeded")

class TestCapability(unittest.TestCase):
    def test_default_deny(self) -> None:
        broker = CapabilityBroker(default_local_fs_manifest())
        denied = broker.authorize(
            role="maker",
            resource="api.example/charge",
            operation="http_call",
            side_effect_class="irreversible",
            idempotency_key="k",
        )
        self.assertFalse(denied.allowed)
        ok = broker.authorize(
            role="maker",
            resource="repo/foo.txt",
            operation="file_write",
            side_effect_class="reversible",
        )
        self.assertTrue(ok.allowed)

class TestSchemas(unittest.TestCase):
    def test_action_claim_and_evidence_roundtrip(self) -> None:
        claim = coerce_document(
            "action_claim",
            {
                "claim_id": "c1",
                "contract_ref": "w1",
                "maker_session_id": "m",
                "intent": "x",
                "alternatives": ["alt"],
                "done_progress": 0.5,
                "confidence": 0.5,
                "world_revision_base": 0,
            },
        )
        self.assertEqual(validate_document("action_claim", claim), [])
        ev = coerce_document(
            "evidence_bundle",
            {
                "evidence_id": "e1",
                "contract_ref": "w1",
                "checker_session_id": "c",
                "artifacts": ["hello.txt"],
                "gaps": [],
                "world_revision": 1,
            },
        )
        self.assertEqual(validate_document("evidence_bundle", ev), [])

class TestRunEngine(unittest.TestCase):
    def test_mock_admit_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            (workdir / "hello.txt").write_text("hi\n", encoding="utf-8")
            engine = RunEngine(
                workdir,
                goal_id="demo",
                goal_title="demo",
                done_criteria=["hello.txt exists"],
            )
            engine.bootstrap()
            claim = {
                "claim_id": "ac1",
                "contract_ref": "tmp",
                "maker_session_id": "maker-sess",
                "intent": "ensure hello",
                "actions": [
                    {
                        "action_id": "a1",
                        "kind": "file_write",
                        "side_effect_class": "reversible",
                        "target": "workdir/hello.txt",
                    }
                ],
                "alternatives": [{"text": "noop", "status": "reject"}],
                "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
                "world_revision_base": 0,
                "payload": {"files": {"hello.txt": "hi\n"}},
            }
            evidence = {
                "evidence_id": "eb1",
                "contract_ref": "tmp",
                "checker_session_id": "checker-sess",
                "world_revision": 1,
                "verdicts": [
                    {
                        "obligation_id": "ob-1",
                        "status": "satisfied",
                        "attestations": [
                            {
                                "method": "file_exists",
                                "world_revision": 1,
                                "digest": "hello",
                                "observer": "checker-sess",
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
            out = engine.step_with_artifacts(claim=claim, evidence=evidence)
            self.assertNotIn("error", out)
            self.assertEqual(out.get("decision", {}).get("decision"), "admit")
            # second step → closure
            out2 = engine.step_with_artifacts(claim=claim, evidence=evidence)
            proj = engine.handler.projection()
            self.assertIn(proj.run_status, {"succeeded", "running"})
            engine.store.verify_hash_chain()
            digest = digest_active_snapshot(workdir)
            self.assertTrue(digest.startswith("sha256:"))
            write_candidate(
                workdir,
                kind="sigma",
                cond="x",
                wrong="y",
                correct="z",
                conf=0.5,
                namespace="demo",
                origin_goal_id="demo",
                origin_run_id="run-1",
            )
            # active digest unchanged (no self-feedback)
            self.assertEqual(digest_active_snapshot(workdir), digest)
            engine.close()

if __name__ == "__main__":
    unittest.main()
