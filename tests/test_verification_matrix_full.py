"""Verification matrix rows §4–§12 — property tests."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.context_audit import run_context_audits
from eglk_harness.domain.kernel.covers import covers_closure_complete
from eglk_harness.domain.kernel.gate import decide
from eglk_harness.domain.kernel.projection_replay import projection_diff, rebuild_from_events, replay_workdir
from eglk_harness.domain.kernel.reducer import reduce_events
from eglk_harness.domain.kernel.run_engine import compile_goal_spec, RunEngine
from eglk_harness.domain.kernel.transaction_audit import (
    audit_run_aborted_chain,
    audit_transaction_sequences,
)
from eglk_harness.domain.product.init_project import init_project


class TestMatrixIntegrityAndAbort(unittest.TestCase):
    def test_integrity_violation_never_admits(self) -> None:
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
            "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
        }
        evidence = {
            "schema": "eglk.evidence_bundle",
            "evidence_id": "e1",
            "contract_ref": "wc-1",
            "checker_session_id": "c1",
            "world_revision": 0,
            "verdicts": [
                {
                    "obligation_id": "ob-1",
                    "status": "satisfied",
                    "attestations": [],
                    "gaps": [],
                }
            ],
            "integrity_violation": True,
        }
        d = decide(contract, claim, evidence)
        self.assertNotEqual(d.decision, "admit")

    def test_run_aborted_audit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            h.run_created(
                goal_id="g",
                memory_digest="sha256:" + "a" * 64,
                cognitive_tokens_max=10,
                repairs_max=1,
            )
            gd = h._append(
                "GateDecided",
                {
                    "decision": "abort",
                    "reason": "cognitive_budget",
                    "node_id": "root",
                    "contract_ref": "wc",
                },
            )
            h._append(
                "RunAborted",
                {"reason": "cognitive_budget"},
                causation_id=gd.event_id,
            )
            ok, detail = audit_run_aborted_chain(store.read_all())
            self.assertTrue(ok, detail)
            store.release_lease(holder="t")
            store.close()

    def test_transaction_sequence_audit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            h.transaction_prepared({"transaction_id": "tx-1", "node_id": "root"})
            h.transaction_observed(
                transaction_id="tx-1",
                world_revision=1,
                observation={},
            )
            h._append(
                "TransactionCommitted",
                {"transaction_id": "tx-1", "world_revision": 1, "touches": []},
            )
            ok, _ = audit_transaction_sequences(store.read_all())
            self.assertTrue(ok)
            store.release_lease(holder="t")
            store.close()


class TestMatrixReplayAndCompile(unittest.TestCase):
    def test_wipe_projections_replay_equivalent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir)
            (workdir / ".goal.md").write_text("# T\n\n- [ ] done\n", encoding="utf-8")
            engine = RunEngine(
                workdir,
                goal_id="g-wipe",
                goal_title="T",
                done_criteria=["done"],
            )
            engine.bootstrap()
            loop = engine.loop_dir
            proj_dir = loop / "projections"
            before = rebuild_from_events(loop)
            shutil.rmtree(proj_dir)
            replay_workdir(workdir, "g-wipe")
            after = rebuild_from_events(loop)
            self.assertEqual([], projection_diff(before["run"], after["run"]))
            engine.close()

    def test_goal_compile_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            text = "# Goal\n\n- [ ] a\n- [ ] b\n"
            a = compile_goal_spec(workdir, goal_id="g", goal_text=text, done_criteria=["a", "b"])
            b = compile_goal_spec(workdir, goal_id="g", goal_text=text, done_criteria=["a", "b"])
            self.assertEqual(
                a["requirements"][0]["obligations"],
                b["requirements"][0]["obligations"],
            )

    def test_context_static_audits(self) -> None:
        pkg = Path(__file__).resolve().parents[1] / "src" / "eglk_harness"
        rows = run_context_audits(pkg)
        self.assertTrue(all(r["ok"] for r in rows), json.dumps(rows, indent=2))


class TestMatrixSessionsPerContract(unittest.TestCase):
    def test_distinct_maker_sessions_per_contract(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            h.action_dispatched(
                {"claim_id": "c1", "contract_ref": "wc-1", "maker_session_id": "m-1"},
                actor="maker",
            )
            h.action_dispatched(
                {"claim_id": "c2", "contract_ref": "wc-2", "maker_session_id": "m-2"},
                actor="maker",
            )
            mapping: dict[str, str] = {}
            for ev in store.read_all():
                if ev.type == "ActionDispatched":
                    p = ev.payload or {}
                    mapping[str(p["maker_session_id"])] = str(p["contract_ref"])
            self.assertEqual(mapping["m-1"], "wc-1")
            self.assertEqual(mapping["m-2"], "wc-2")
            self.assertNotEqual(mapping["m-1"], mapping["m-2"])
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
