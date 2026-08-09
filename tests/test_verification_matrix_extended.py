"""Extended verification_matrix.md property tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.projection_mirror import mirror_audit_artifacts
from eglk_harness.domain.kernel.projection_replay import projection_diff, rebuild_from_events
from eglk_harness.domain.kernel.recovery import reconcile_dangling_transactions
from eglk_harness.domain.kernel.reducer import reduce_events, run_projection_dict
from eglk_harness.domain.kernel.session_policy import validate_maker_session
from eglk_harness.domain.memory.lifecycle import write_candidate


class TestVerificationMatrixExtended(unittest.TestCase):
    def test_goal_drift_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            goal = workdir / ".goal.md"
            goal.write_text("version one\n", encoding="utf-8")
            loop_dir = Path(td) / "loop" / "g-test"
            loop_dir.mkdir(parents=True, exist_ok=True)
            store = EventStore(loop_dir / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            from eglk_harness.domain.kernel.run_engine import _goal_digest

            digest = _goal_digest("version one\n")
            h.run_created(
                goal_id="g-test",
                memory_digest="sha256:" + "a" * 64,
                cognitive_tokens_max=1000,
                repairs_max=8,
            )
            h.goal_compiled(
                {
                    "source_digest": digest,
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
            goal.write_text("version two\n", encoding="utf-8")
            drift = h.check_goal_drift(workdir)
            self.assertFalse(drift.ok)
            types = [e.type for e in store.read_all()]
            self.assertIn("RunInvalid", types)
            store.release_lease(holder="t")
            store.close()

    def test_session_reuse_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            h.action_dispatched(
                {
                    "claim_id": "c1",
                    "contract_ref": "wc-1",
                    "maker_session_id": "sess-a",
                },
                actor="maker",
            )
            bad = h.action_dispatched(
                {
                    "claim_id": "c2",
                    "contract_ref": "wc-2",
                    "maker_session_id": "sess-a",
                },
                actor="maker",
            )
            self.assertFalse(bad.ok)
            ok, reason = validate_maker_session(
                {"contract_ref": "wc-2", "maker_session_id": "sess-a"},
                store.read_all(),
            )
            self.assertFalse(ok)
            self.assertEqual(reason, "session_reused_across_contracts")
            store.release_lease(holder="t")
            store.close()

    def test_recovery_dangling_transaction(self) -> None:
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
            h.transaction_prepared({"transaction_id": "tx-1", "node_id": "root"})
            out = reconcile_dangling_transactions(h)
            self.assertTrue(out["recovered"])
            self.assertEqual(out["dangling"], ["tx-1"])
            types = [e.type for e in store.read_all()]
            self.assertIn("RunRecoveryStarted", types)
            self.assertIn("TransactionRolledBack", types)
            store.release_lease(holder="t")
            store.close()

    def test_replay_projection_equivalence_after_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            loop = Path(td)
            store = EventStore(loop / "events.db")
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
            exported = h.export_projections()
            replay = rebuild_from_events(loop)
            self.assertEqual([], projection_diff(exported["run"], replay["run"]))
            store.release_lease(holder="t")
            store.close()

    def test_audit_mirror_from_events(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            loop = Path(td)
            store = EventStore(loop / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            h.action_dispatched(
                {
                    "claim_id": "c1",
                    "contract_ref": "wc-1",
                    "maker_session_id": "m-1",
                    "claim": {"claim_id": "c1"},
                },
                actor="maker",
            )
            h.record_evidence(
                {
                    "evidence_id": "e1",
                    "contract_ref": "wc-1",
                    "checker_session_id": "c-1",
                },
                actor="checker",
            )
            h._append("GateDecided", {"decision": "repair", "reason": "test"})
            paths = mirror_audit_artifacts(loop, store.read_all(), tick=0)
            self.assertIn("claim", paths)
            claim = json.loads(Path(paths["claim"]).read_text(encoding="utf-8"))
            self.assertEqual(claim.get("_mirror", {}).get("authority"), "events.db")
            store.release_lease(holder="t")
            store.close()

    def test_memory_candidate_event(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
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
                origin_run_id="run-1",
                handler=h,
            )
            types = [e.type for e in store.read_all()]
            self.assertIn("MemoryCandidateWritten", types)
            self.assertTrue(any(e.payload.get("record_id") == rec["id"] for e in store.read_all()))
            store.release_lease(holder="t")
            store.close()

    def test_quota_updated_per_role(self) -> None:
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
            for role in ("maker", "checker", "governor", "explorer"):
                h.quota_updated(role=role, tokens_delta=10)
            proj = reduce_events(store.read_all())
            self.assertGreaterEqual(proj.cognitive_tokens_by_role.get("maker", 0), 10)
            self.assertGreaterEqual(proj.cognitive_tokens_by_role.get("explorer", 0), 10)
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
