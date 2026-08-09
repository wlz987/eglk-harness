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


class TestAttestationFloor(unittest.TestCase):
    def test_missing_observer_rejected(self) -> None:
        from eglk_harness.domain.kernel.attestation import attestation_structurally_valid

        self.assertFalse(
            attestation_structurally_valid(
                {
                    "method": "file_exists",
                    "world_revision": 1,
                    "digest": "x",
                    "observer": "",
                    "raw_ref": "a",
                    "watch_set": [],
                }
            )
        )

    def test_method_must_match_verification_type(self) -> None:
        from eglk_harness.domain.kernel.attestation import method_allowed_for_verification_type

        self.assertFalse(method_allowed_for_verification_type("api_state", "file_exists"))
        self.assertTrue(method_allowed_for_verification_type("file_exists", "file_exists"))
        self.assertTrue(method_allowed_for_verification_type("custom_attestation", "file_exists"))

    def test_gate_rejects_revision_mismatch(self) -> None:
        g = TestGate()
        ev = g._evidence(satisfied=True)
        ev["verdicts"][0]["attestations"][0]["world_revision"] = 99
        d = decide(g._contract(), g._claim(), ev)
        self.assertEqual(d.decision, "repair")
        self.assertEqual(d.reason, "no_attestation")


class TestRepairFeedback(unittest.TestCase):
    def test_extract_and_load(self) -> None:
        from eglk_harness.domain.kernel.repair_feedback import (
            extract_repair_feedback,
            load_prior_repair_feedback,
            repair_feedback_as_prior_evidence,
        )

        fb = extract_repair_feedback(
            evidence={
                "verdicts": [
                    {
                        "obligation_id": "ob-1",
                        "status": "unsatisfied",
                        "gaps": ["need artifact"],
                        "attestations": [],
                        "defect_suspected": False,
                    }
                ],
                "additional_gaps": ["boundary:forbidden"],
            },
            decision={"decision": "repair", "reason": "no_attestation", "open_obligation_ids": ["ob-1"]},
        )
        self.assertIsNotNone(fb)
        assert fb is not None
        self.assertEqual(fb["prior_decision"], "repair")
        self.assertIn("need artifact", fb["gaps"])
        priors = repair_feedback_as_prior_evidence(fb)
        self.assertTrue(any(p.get("kind") == "gap" for p in priors))

        with tempfile.TemporaryDirectory() as td:
            loop = Path(td)
            (loop / "decisions").mkdir(parents=True)
            (loop / "evidence").mkdir(parents=True)
            (loop / "decisions" / "000.json").write_text(
                json.dumps({"decision": "repair", "reason": "no_attestation", "open_obligation_ids": ["ob-1"]}),
                encoding="utf-8",
            )
            (loop / "evidence" / "000.json").write_text(
                json.dumps(
                    {
                        "verdicts": [
                            {
                                "obligation_id": "ob-1",
                                "status": "unsatisfied",
                                "gaps": ["x"],
                                "attestations": [],
                                "defect_suspected": False,
                            }
                        ],
                        "additional_gaps": [],
                    }
                ),
                encoding="utf-8",
            )
            loaded = load_prior_repair_feedback(loop, current_tick=1)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["reason"], "no_attestation")


class TestObligationCompile(unittest.TestCase):
    def test_coarse_conservative(self) -> None:
        from eglk_harness.domain.kernel.obligation_compile import (
            choose_root_verification_type,
            compile_root_obligations,
        )

        self.assertEqual(choose_root_verification_type("Get the total number of reviews"), "custom_attestation")
        self.assertEqual(choose_root_verification_type("MUST_EXIST out/report.json"), "file_exists")
        obs = compile_root_obligations(["Satisfy intent", "Leave inspectable artifacts"])
        self.assertTrue(all(o["origin"] == "root" for o in obs))
        self.assertTrue(all(o["verification_type"] == "custom_attestation" for o in obs))


class TestAdvisorGuard(unittest.TestCase):
    def test_blocks_evidence_write(self) -> None:
        from eglk_harness.domain.kernel.advisor_guard import assert_advisor_path_allowed

        with tempfile.TemporaryDirectory() as td:
            loop = Path(td)
            (loop / "evidence").mkdir()
            with self.assertRaises(PermissionError):
                assert_advisor_path_allowed(loop / "evidence" / "000.json", loop_dir=loop)


class TestAmendment(unittest.TestCase):
    def test_root_immutable_derived_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            (workdir / ".goal.md").write_text("# G\n\n- done\n", encoding="utf-8")
            init_project(workdir)
            engine = RunEngine(workdir, goal_id="g-am", goal_title="G", done_criteria=["done"])
            engine.bootstrap()
            # open a derived obligation under root
            root_obs = [oid for oid, ob in engine.handler.projection().obligations.items() if ob.origin == "root"]
            self.assertTrue(root_obs)
            root_id = root_obs[0]
            engine.handler._append(
                "ObligationOpened",
                {
                    "obligation_id": "ob-derived-1",
                    "requirement_id": "req-1",
                    "parent_obligation_id": root_id,
                    "statement": "coarse derived",
                    "verification_type": "custom_attestation",
                    "origin": "derived",
                },
            )
            bad = engine.handler.propose_obligation_amendment(
                obligation_id=root_id,
                new_statement="should fail",
            )
            self.assertFalse(bad.ok)
            ok = engine.handler.propose_obligation_amendment(
                obligation_id="ob-derived-1",
                new_statement="refined derived statement",
                new_verification_type="file_exists",
            )
            self.assertTrue(ok.ok)
            proj = engine.handler.projection()
            self.assertEqual(proj.obligations["ob-derived-1"].statement, "refined derived statement")
            self.assertEqual(proj.obligations["ob-derived-1"].verification_type, "file_exists")
            engine.close()


class TestObserve(unittest.TestCase):
    def test_observe_read_only_bundle(self) -> None:
        from eglk_harness.domain.environment.world_transaction import LocalFilesystemAdapter

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workdir = root / "work"
            world = root / "world"
            workdir.mkdir()
            (workdir / "hello.txt").write_text("hi", encoding="utf-8")
            adapter = LocalFilesystemAdapter(workdir, world)
            tx = adapter.begin(node_id="n", base_revision=0, side_effect_class="read_only")
            tx = adapter.prepare(tx, [{"action_id": "a1", "side_effect_class": "read_only"}])
            tx = adapter.apply(tx, claim_payload=None)
            tx.touches = ["hello.txt"]
            tx.candidate_revision = 1
            obs = adapter.observe(tx)
            self.assertEqual(obs["side_effect_class"], "read_only")
            self.assertEqual(obs["world_revision"], 1)
            self.assertTrue(any(f.get("path") == "hello.txt" for f in obs["files"]))


if __name__ == "__main__":
    unittest.main()
