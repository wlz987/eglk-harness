"""Integration tests for verification_matrix §7–§12 (replay, covers, tx, memory)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.capability import CapabilityBroker, CapabilityEntry, CapabilityManifest
from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.covers import covers_closure_complete
from eglk_harness.domain.kernel.gate import decide
from eglk_harness.domain.kernel.projection_replay import projection_diff, rebuild_from_events
from eglk_harness.domain.kernel.reducer import reduce_events, run_projection_dict
from eglk_harness.domain.kernel.transaction_audit import audit_transaction_sequences
from eglk_harness.domain.memory.lifecycle import (
    bump_verification,
    promote,
    quarantine_candidates,
    write_candidate,
)
from eglk_harness.domain.product.init_project import init_project


def _attestation(observer: str = "c-1") -> dict:
    return {
        "method": "custom_attestation",
        "world_revision": 1,
        "digest": "sha256:" + "c" * 64,
        "observer": observer,
        "raw_ref": "workdir/artifact",
        "watch_set": ["workdir/artifact"],
    }


def _satisfied_verdict(obligation_id: str, *, observer: str = "c-1") -> dict:
    return {
        "obligation_id": obligation_id,
        "status": "satisfied",
        "attestations": [_attestation(observer)],
        "gaps": [],
    }


def _boot_handler(td: str, *, broker: CapabilityBroker | None = None) -> tuple[CommandHandler, EventStore]:
    store = EventStore(Path(td) / "events.db")
    store.acquire_lease(holder="t")
    h = CommandHandler(store, broker=broker)
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
                    "statement": "done",
                    "verification_type": "custom_attestation",
                    "status": "open",
                    "origin": "root",
                }
            ],
        }
    )
    return h, store


class TestIncrementalReducer(unittest.TestCase):
    def test_incremental_matches_full_reduce(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td)
            h.node_ready("root")
            h.quota_updated(role="maker", tokens_delta=5)
            h.quota_updated(role="checker", tokens_delta=3)
            incremental = h.projection()
            full = reduce_events(store.read_all())
            self.assertEqual(
                run_projection_dict(incremental),
                run_projection_dict(full),
            )
            store.release_lease(holder="t")
            store.close()


class TestCoversClosure(unittest.TestCase):
    def test_closure_after_obligation_satisfied(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td)
            h.node_ready("root")
            contract = {
                "schema": "eglk.work_contract",
                "contract_id": "wc-1",
                "node_id": "root",
                "obligation_refs": ["ob-1"],
                "boundary": {"allowed_scope": ["workdir/**"], "forbidden_actions": []},
                "transaction_policy": {"side_effect_class_ceiling": ["reversible"]},
            }
            claim = {
                "schema": "eglk.action_claim",
                "claim_id": "ac-1",
                "contract_ref": "wc-1",
                "maker_session_id": "m-1",
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
                "verdicts": [_satisfied_verdict("ob-1")],
            }
            h.gate_decide(contract=contract, claim=claim, evidence=evidence)
            proj = h.projection()
            self.assertEqual(proj.obligations["ob-1"].status, "satisfied")
            self.assertTrue(covers_closure_complete(proj))
            store.release_lease(holder="t")
            store.close()

    def test_closure_via_derived_obligations(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td)
            h.node_ready("root")
            h.commit_split(
                {
                    "split_node": "root",
                    "children": [
                        {"id": "root.01", "title": "a", "obligation_refs": ["ob-1.1"], "depth": 1},
                        {"id": "root.02", "title": "b", "obligation_refs": ["ob-1.2"], "depth": 1},
                    ],
                    "opened_obligations": [
                        {
                            "id": "ob-1.1",
                            "requirement_id": "req-1",
                            "parent_obligation_id": "ob-1",
                            "statement": "part a",
                            "verification_type": "custom_attestation",
                            "origin": "derived",
                        },
                        {
                            "id": "ob-1.2",
                            "requirement_id": "req-1",
                            "parent_obligation_id": "ob-1",
                            "statement": "part b",
                            "verification_type": "custom_attestation",
                            "origin": "derived",
                        },
                    ],
                    "coverage_proof": {
                        "parent_obligation_ids": ["ob-1"],
                        "child_obligation_map": {},
                        "proof_kind": "refinement",
                    },
                }
            )
            for oid in ("ob-1.1", "ob-1.2"):
                contract = {
                    "schema": "eglk.work_contract",
                    "contract_id": f"wc-{oid}",
                    "node_id": "root.01" if oid == "ob-1.1" else "root.02",
                    "obligation_refs": [oid],
                    "boundary": {"allowed_scope": ["workdir/**"], "forbidden_actions": []},
                    "transaction_policy": {"side_effect_class_ceiling": ["reversible"]},
                }
                claim = {
                    "schema": "eglk.action_claim",
                    "claim_id": f"ac-{oid}",
                    "contract_ref": f"wc-{oid}",
                    "maker_session_id": f"m-{oid}",
                    "actions": [],
                    "alternatives": [{"text": "x", "status": "reject"}],
                    "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
                }
                evidence = {
                    "schema": "eglk.evidence_bundle",
                    "evidence_id": f"e-{oid}",
                    "contract_ref": f"wc-{oid}",
                    "checker_session_id": f"c-{oid}",
                    "world_revision": 1,
                    "verdicts": [_satisfied_verdict(oid, observer=f"c-{oid}")],
                }
                h.gate_decide(contract=contract, claim=claim, evidence=evidence)
            proj = h.projection()
            self.assertTrue(covers_closure_complete(proj))
            store.release_lease(holder="t")
            store.close()


class TestIrreversibleTransaction(unittest.TestCase):
    def _irreversible_broker(self) -> CapabilityBroker:
        manifest = CapabilityManifest(
            schema="eglk.capability_manifest",
            manifest_id="test-irreversible",
            default_deny=True,
            entries=[
                CapabilityEntry(
                    id="maker-api-irrev",
                    role="maker",
                    resource="api/**",
                    operation="http_call",
                    allowed_side_effect_classes=("irreversible",),
                    requires_idempotency_key=True,
                )
            ],
        )
        return CapabilityBroker(manifest)

    def test_irreversible_tx_sequence_valid(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td, broker=self._irreversible_broker())
            action = {
                "action_id": "a-ir",
                "kind": "http_call",
                "side_effect_class": "irreversible",
                "target": "api/charge",
                "idempotency_key": "idem-1",
            }
            ok = h.authorize_actions(
                role="maker",
                actions=[action],
                ceiling=["read_only", "reversible", "irreversible"],
            )
            self.assertTrue(ok.ok)
            h.transaction_prepared(
                {
                    "transaction_id": "tx-ir",
                    "node_id": "root",
                    "side_effect_class": "irreversible",
                }
            )
            h.transaction_observed(
                transaction_id="tx-ir",
                world_revision=1,
                observation={"status": "applied"},
            )
            h._append(
                "TransactionCommitted",
                {
                    "transaction_id": "tx-ir",
                    "world_revision": 1,
                    "touches": ["api/charge"],
                },
            )
            passed, detail = audit_transaction_sequences(store.read_all())
            self.assertTrue(passed, detail)
            store.release_lease(holder="t")
            store.close()

    def test_irreversible_without_prepare_fails_audit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td)
            h._append(
                "TransactionCommitted",
                {"transaction_id": "tx-skip", "world_revision": 1, "touches": []},
            )
            passed, detail = audit_transaction_sequences(store.read_all())
            self.assertFalse(passed)
            self.assertIn("tx-skip", detail)
            store.release_lease(holder="t")
            store.close()

    def test_irreversible_without_idempotency_denied(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td, broker=self._irreversible_broker())
            bad = h.authorize_actions(
                role="maker",
                actions=[
                    {
                        "action_id": "a-ir",
                        "kind": "http_call",
                        "side_effect_class": "irreversible",
                        "target": "api/charge",
                    }
                ],
                ceiling=["irreversible"],
            )
            self.assertFalse(bad.ok)
            types = [e.type for e in store.read_all()]
            self.assertIn("CapabilityDenied", types)
            store.release_lease(holder="t")
            store.close()


class TestMemoryLifecycle(unittest.TestCase):
    def test_candidate_to_active_events(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir)
            store = EventStore(workdir / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            rec = write_candidate(
                workdir,
                kind="sigma",
                cond="c",
                wrong="w",
                correct="r",
                conf=0.9,
                namespace="n",
                origin_goal_id="g",
                origin_run_id="run-origin",
                handler=h,
            )
            rid = str(rec["id"])
            n = quarantine_candidates(workdir, handler=h)
            self.assertEqual(1, n)
            bump_verification(workdir, rid)
            bump_verification(workdir, rid)
            promote(workdir, rid, to_status="verified", handler=h, actor="refiner")
            active = promote(
                workdir,
                rid,
                to_status="active",
                by_run_id="run-promoter",
                handler=h,
                actor="refiner",
            )
            self.assertIsNotNone(active)
            self.assertEqual(active["lifecycle_status"], "active")
            active_path = workdir / ".eglk-harness" / "memory" / "sigma" / "active" / f"{rid}.json"
            self.assertTrue(active_path.is_file())
            promoted = [e for e in store.read_all() if e.type == "MemoryPromoted"]
            self.assertGreaterEqual(len(promoted), 3)
            transitions = {
                (str((e.payload or {}).get("from_status")), str((e.payload or {}).get("to_status")))
                for e in promoted
            }
            self.assertIn(("candidate", "quarantined"), transitions)
            self.assertIn(("quarantined", "verified"), transitions)
            self.assertIn(("verified", "active"), transitions)
            store.release_lease(holder="t")
            store.close()


class TestClosureGateE2E(unittest.TestCase):
    def test_event_runtime_closure_gate_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            from eglk_harness.domain.kernel.event_runtime import RunEventContext

            ctx = RunEventContext(workdir, "g-close")
            ctx.acquire()
            ctx.bootstrap_if_needed(goal_title="t", done_criteria=["done"])
            # Closure Gate requires real watch_set files (no synthetic digests).
            art = workdir / "artifact"
            art.write_text("ok\n", encoding="utf-8")
            ctx.handler.node_ready("root")
            contract = {
                "schema": "eglk.work_contract",
                "contract_id": "wc-1",
                "node_id": "root",
                "obligation_refs": ["ob-1"],
                "boundary": {"allowed_scope": ["workdir/**"], "forbidden_actions": []},
                "transaction_policy": {"side_effect_class_ceiling": ["reversible"]},
            }
            claim = {
                "schema": "eglk.action_claim",
                "claim_id": "ac-1",
                "contract_ref": "wc-1",
                "maker_session_id": "m-1",
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
                "verdicts": [_satisfied_verdict("ob-1")],
            }
            ctx.contract_assembled(contract)
            ctx.dispatch_claim(claim, actor="maker")
            ctx.record_evidence(evidence, actor="checker")
            ctx.gate_decide(claim=claim, evidence=evidence)
            self.assertTrue(ctx.closure_needed())
            closure = ctx.run_closure_gate()
            self.assertTrue(closure.ok)
            proj = ctx.handler.projection()
            self.assertEqual(proj.run_status, "succeeded")
            types = [e.type for e in ctx.store.read_all()]
            self.assertIn("RunSucceeded", types)
            ctx.release()

    def test_incremental_projection_large_stream(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td)
            roles = ("maker", "checker", "governor", "explorer", "verifier", "refiner")
            for i in range(120):
                h.quota_updated(role=roles[i % len(roles)], tokens_delta=1)
            incremental = h.projection()
            full = reduce_events(store.read_all())
            self.assertEqual(run_projection_dict(incremental), run_projection_dict(full))
            exported = h.export_projections()
            replay = rebuild_from_events(Path(td))
            self.assertEqual([], projection_diff(exported["run"], replay["run"]))
            store.release_lease(holder="t")
            store.close()


class TestInvalidateSameRevision(unittest.TestCase):
    def test_satisfied_at_commit_revision_not_invalidated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td)
            h.node_ready("root")
            contract = {
                "schema": "eglk.work_contract",
                "contract_id": "wc-1",
                "node_id": "root",
                "obligation_refs": ["ob-1"],
                "boundary": {"allowed_scope": ["workdir/**"], "forbidden_actions": []},
                "transaction_policy": {"side_effect_class_ceiling": ["reversible"]},
            }
            claim = {
                "schema": "eglk.action_claim",
                "claim_id": "ac-1",
                "contract_ref": "wc-1",
                "maker_session_id": "m-1",
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
            h.invalidate_from_commit(
                touches=["workdir/hello.txt"],
                transaction_id="tx-1",
                world_revision=1,
            )
            proj = h.projection()
            self.assertEqual(proj.obligations["ob-1"].status, "satisfied")
            types = [e.type for e in store.read_all()]
            self.assertNotIn("ObligationInvalidated", types)
            store.release_lease(holder="t")
            store.close()


class TestFullRunReplay(unittest.TestCase):
    def test_export_then_wipe_replay_empty_diff(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td)
            h.node_ready("root")
            h.quota_updated(role="governor", tokens_delta=3)
            h.quota_updated(role="explorer", tokens_delta=2)
            exported = h.export_projections()
            loop = Path(td)
            replay = rebuild_from_events(loop)
            self.assertEqual([], projection_diff(exported["run"], replay["run"]))
            self.assertEqual([], projection_diff(exported.get("task_structure"), replay.get("task_structure")))
            store.release_lease(holder="t")
            store.close()


class TestCompensatableTransaction(unittest.TestCase):
    def _comp_broker(self) -> CapabilityBroker:
        manifest = CapabilityManifest(
            schema="eglk.capability_manifest",
            manifest_id="test-compensatable",
            default_deny=True,
            entries=[
                CapabilityEntry(
                    id="maker-file-comp",
                    role="maker",
                    resource="workdir/**",
                    operation="file_write",
                    allowed_side_effect_classes=("compensatable",),
                )
            ],
        )
        return CapabilityBroker(manifest)

    def test_repair_compensates_and_audits(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            from eglk_harness.domain.kernel.event_runtime import RunEventContext

            ctx = RunEventContext(workdir, "g-comp")
            ctx.broker = self._comp_broker()
            ctx.handler.broker = ctx.broker
            ctx.acquire()
            ctx.bootstrap_if_needed(goal_title="comp", done_criteria=["comp.txt"])
            ctx.handler.node_ready("root")
            contract = ctx.assemble_contract_for_node("root")
            policy = dict(contract.get("transaction_policy") or {})
            policy["side_effect_class_ceiling"] = ["read_only", "reversible", "compensatable"]
            contract["transaction_policy"] = policy
            ctx.contract_assembled(contract)
            claim = {
                "schema": "eglk.action_claim",
                "claim_id": "ac-comp",
                "contract_ref": contract["contract_id"],
                "maker_session_id": "m-comp",
                "actions": [
                    {
                        "action_id": "write-comp",
                        "kind": "file_write",
                        "side_effect_class": "compensatable",
                        "target": "workdir/comp.txt",
                        "payload": {"path": "comp.txt", "content": "comp line\n"},
                    }
                ],
                "alternatives": [{"text": "skip", "status": "reject"}],
                "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
            }
            self.assertTrue(ctx.authorize_maker(claim).ok)
            ctx.dispatch_claim(claim, actor="maker")
            tx = ctx.apply_claim_to_tx(claim)
            self.assertTrue((workdir / "comp.txt").is_file())
            evidence = {
                "schema": "eglk.evidence_bundle",
                "evidence_id": "ev-comp",
                "contract_ref": contract["contract_id"],
                "checker_session_id": "c-comp",
                "world_revision": ctx.env.observe_revision(tx),
                "verdicts": [
                    {
                        "obligation_id": "ob-1",
                        "status": "unsatisfied",
                        "attestations": [],
                        "gaps": ["not done yet"],
                    }
                ],
            }
            ctx.record_evidence(evidence, actor="checker")
            gd = ctx.gate_decide(claim=claim, evidence=evidence)
            decision = str((gd.events[0].payload or {}).get("decision") or "")
            self.assertEqual(decision, "repair")
            ctx.finalize_transaction_after_gate(decision)
            types = [e.type for e in ctx.store.read_all()]
            self.assertIn("TransactionCompensated", types)
            passed, detail = audit_transaction_sequences(ctx.store.read_all())
            self.assertTrue(passed, detail)
            self.assertFalse((workdir / "comp.txt").is_file())
            ctx.release()


class TestAmendmentPendingGate(unittest.TestCase):
    def test_pending_amendment_blocks_until_amended(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td)
            h.node_ready("root")
            h._append(
                "ObligationOpened",
                {
                    "obligation_id": "ob-derived",
                    "requirement_id": "req-1",
                    "parent_obligation_id": "ob-1",
                    "statement": "derived coarse",
                    "verification_type": "custom_attestation",
                    "origin": "derived",
                },
            )
            h._append(
                "ObligationAmendmentProposed",
                {
                    "obligation_id": "ob-derived",
                    "old_statement": "derived coarse",
                    "new_statement": "derived refined",
                    "new_verification_type": "file_exists",
                    "coverage_proof": {"kind": "refinement", "parent": "ob-1"},
                },
            )
            proj = h.projection()
            self.assertIn("ob-derived", proj.pending_amendments)
            contract = {
                "schema": "eglk.work_contract",
                "contract_id": "wc-der",
                "node_id": "root",
                "obligation_refs": ["ob-derived"],
                "boundary": {"allowed_scope": ["workdir/**"], "forbidden_actions": []},
                "transaction_policy": {"side_effect_class_ceiling": ["reversible"]},
            }
            claim = {
                "schema": "eglk.action_claim",
                "claim_id": "ac-der",
                "contract_ref": "wc-der",
                "maker_session_id": "m-der",
                "actions": [],
                "alternatives": [{"text": "x", "status": "reject"}],
                "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
            }
            evidence = {
                "schema": "eglk.evidence_bundle",
                "evidence_id": "ev-der",
                "contract_ref": "wc-der",
                "checker_session_id": "c-der",
                "world_revision": 1,
                "verdicts": [
                    {
                        "obligation_id": "ob-derived",
                        "status": "satisfied",
                        "attestations": [_attestation("c-der")],
                        "gaps": [],
                    }
                ],
            }
            blocked = h.gate_decide(contract=contract, claim=claim, evidence=evidence)
            self.assertEqual((blocked.events[0].payload or {}).get("reason"), "amendment_pending")
            h._append(
                "ObligationAmended",
                {
                    "obligation_id": "ob-derived",
                    "old_statement": "derived coarse",
                    "new_statement": "derived refined",
                    "new_verification_type": "file_exists",
                    "parent_obligation_id": "ob-1",
                },
            )
            admitted = h.gate_decide(contract=contract, claim=claim, evidence=evidence)
            self.assertEqual((admitted.events[0].payload or {}).get("decision"), "admit")
            store.release_lease(holder="t")
            store.close()


class TestCompensatableRecovery(unittest.TestCase):
    def test_dangling_prepared_tx_reconciled_on_acquire(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td)
            h.node_ready("root")
            h.transaction_prepared(
                {
                    "transaction_id": "tx-dangle",
                    "node_id": "root",
                    "side_effect_class": "compensatable",
                }
            )
            from eglk_harness.domain.kernel.recovery import reconcile_dangling_transactions

            out = reconcile_dangling_transactions(h)
            self.assertTrue(out.get("recovered"))
            self.assertIn("tx-dangle", out.get("dangling") or [])
            types = [e.type for e in store.read_all()]
            self.assertIn("TransactionRolledBack", types)
            store.release_lease(holder="t")
            store.close()


class TestEventLogHashConsistency(unittest.TestCase):
    def test_projection_last_hash_matches_event_tip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td)
            h.node_ready("root")
            h.quota_updated(role="maker", tokens_delta=2)
            h.quota_updated(role="checker", tokens_delta=1)
            proj = h.projection()
            events = store.read_all()
            self.assertTrue(events)
            self.assertEqual(proj.last_hash, events[-1].hash)
            exported = h.export_projections()["run"]
            self.assertEqual(exported.get("last_hash"), events[-1].hash)
            store.release_lease(holder="t")
            store.close()


class TestIrreversibleRunEnd(unittest.TestCase):
    def _irreversible_broker(self) -> CapabilityBroker:
        manifest = CapabilityManifest(
            schema="eglk.capability_manifest",
            manifest_id="test-irreversible-e2e",
            default_deny=True,
            entries=[
                CapabilityEntry(
                    id="maker-api-irrev",
                    role="maker",
                    resource="api/**",
                    operation="http_call",
                    allowed_side_effect_classes=("irreversible",),
                    requires_idempotency_key=True,
                )
            ],
        )
        return CapabilityBroker(manifest)

    def test_repair_does_not_roll_back_irreversible(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            from eglk_harness.domain.kernel.event_runtime import RunEventContext

            ctx = RunEventContext(workdir, "g-irrev")
            ctx.broker = self._irreversible_broker()
            ctx.handler.broker = ctx.broker
            ctx.acquire()
            ctx.bootstrap_if_needed(goal_title="irrev", done_criteria=["done"])
            ctx.handler.node_ready("root")
            contract = ctx.assemble_contract_for_node("root")
            policy = dict(contract.get("transaction_policy") or {})
            policy["side_effect_class_ceiling"] = ["read_only", "reversible", "irreversible"]
            contract["transaction_policy"] = policy
            ctx.contract_assembled(contract)
            claim = {
                "schema": "eglk.action_claim",
                "claim_id": "ac-ir",
                "contract_ref": contract["contract_id"],
                "maker_session_id": "m-ir",
                "actions": [
                    {
                        "action_id": "a-ir",
                        "kind": "http_call",
                        "side_effect_class": "irreversible",
                        "target": "api/charge",
                        "idempotency_key": "idem-ir-1",
                    }
                ],
                "alternatives": [{"text": "skip", "status": "reject"}],
                "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
            }
            self.assertTrue(ctx.authorize_maker(claim).ok)
            ctx.dispatch_claim(claim, actor="maker")
            tx = ctx.apply_claim_to_tx(claim)
            evidence = {
                "schema": "eglk.evidence_bundle",
                "evidence_id": "ev-ir",
                "contract_ref": contract["contract_id"],
                "checker_session_id": "c-ir",
                "world_revision": ctx.env.observe_revision(tx),
                "verdicts": [
                    {
                        "obligation_id": "ob-1",
                        "status": "unsatisfied",
                        "attestations": [],
                        "gaps": ["pending"],
                    }
                ],
            }
            ctx.record_evidence(evidence, actor="checker")
            gd = ctx.gate_decide(claim=claim, evidence=evidence)
            self.assertEqual(str((gd.events[0].payload or {}).get("decision")), "repair")
            ctx.finalize_transaction_after_gate("repair")
            types = [e.type for e in ctx.store.read_all()]
            self.assertNotIn("TransactionRolledBack", types)
            self.assertNotIn("TransactionCompensated", types)
            ctx.release()


class TestRunEndRefinerBatch(unittest.TestCase):
    def test_terminal_run_flushes_staged_to_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            from eglk_harness.domain.adapters.mock import MockAdapter
            from eglk_harness.domain.kernel.event_runtime import RunEventContext
            from eglk_harness.domain.memory.refiner_batch import run_end_refiner_batch
            from eglk_harness.domain.memory import sigma

            gid = "g-ref-end"
            loop_dir = paths.ensure_loop_layout(workdir, gid)
            sigma.write_refined(loop_dir, 0, {"id": "s0", "kind": "hit", "text": "t", "conf": 0.7})

            ctx = RunEventContext(workdir, gid)
            ctx.acquire()
            ctx.bootstrap_if_needed(goal_title="t", done_criteria=["done"])
            ctx.handler.node_ready("root")
            ctx.handler._append("RunSucceeded", {"reason": "closure_admitted"})
            ctx.export_projections()
            ctx.release()

            out = asyncio.run(run_end_refiner_batch(workdir, gid, MockAdapter()))
            self.assertTrue(out.get("ok"))
            self.assertGreaterEqual(int(out.get("flushed_to_candidate") or 0), 1)
            cand_dir = workdir / ".eglk-harness" / "memory" / "sigma" / "candidate"
            self.assertTrue(any(cand_dir.glob("*.json")))


class TestTickQuotaRolesIntegration(unittest.TestCase):
    def test_refiner_and_candidate_selector_quota_events(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            h, store = _boot_handler(td)
            h.node_ready("root")
            for role in (
                "maker",
                "checker",
                "governor",
                "explorer",
                "verifier",
                "candidate_selector",
                "refiner",
            ):
                h.quota_updated(role=role, tokens_delta=3)
            proj = h.projection()
            for role in (
                "maker",
                "checker",
                "governor",
                "explorer",
                "verifier",
                "candidate_selector",
                "refiner",
            ):
                self.assertGreaterEqual(proj.cognitive_tokens_by_role.get(role, 0), 3)
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
