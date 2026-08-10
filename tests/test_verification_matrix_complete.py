"""verification_matrix.md — all 12 invariants have automated assertions."""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.context_audit import run_context_audits
from eglk_harness.domain.kernel.coverage_proof import validate_merge_obligations
from eglk_harness.domain.kernel.gate import decide, ABORT_REASONS
from eglk_harness.domain.kernel.projection_replay import projection_diff, rebuild_from_events, replay_workdir
from eglk_harness.domain.kernel.reducer import reduce_events
from eglk_harness.domain.kernel.run_engine import compile_goal_spec, _goal_digest
from eglk_harness.domain.kernel.session_policy import validate_maker_session
from eglk_harness.domain.kernel.transaction_audit import audit_run_aborted_chain, audit_transaction_sequences
from eglk_harness.domain.product.init_project import init_project


_PKG = Path(__file__).resolve().parents[1] / "src" / "eglk_harness"
_SCHEMA_DIR = _PKG / "domain" / "schemas"


class TestMatrixRow01GoalSsot(unittest.TestCase):
    def test_goal_drift_and_idempotent_compile(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            goal = workdir / ".goal.md"
            goal.write_text("version one\n", encoding="utf-8")
            loop_dir = Path(td) / "loop" / "g1"
            loop_dir.mkdir(parents=True)
            store = EventStore(loop_dir / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            digest = _goal_digest("version one\n")
            h.run_created(goal_id="g1", memory_digest="sha256:" + "a" * 64, cognitive_tokens_max=100, repairs_max=8)
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
            dup = h.goal_compiled(
                {
                    "source_digest": digest,
                    "root_node_id": "root",
                    "title": "t",
                    "obligation_refs": ["ob-1"],
                    "obligations": [],
                }
            )
            self.assertTrue(dup.ok)
            self.assertEqual(len(dup.events), 0)
            goal.write_text("version two\n", encoding="utf-8")
            drift = h.check_goal_drift(workdir)
            self.assertFalse(drift.ok)
            types = [e.type for e in store.read_all()]
            self.assertEqual(types.count("GoalCompiled"), 1)
            self.assertIn("RunInvalid", types)
            store.release_lease(holder="t")
            store.close()

            text = "# Goal\n\n- [ ] a\n"
            a = compile_goal_spec(workdir, goal_id="g", goal_text=text, done_criteria=["a"])
            b = compile_goal_spec(workdir, goal_id="g", goal_text=text, done_criteria=["a"])
            self.assertEqual(a["requirements"][0]["obligations"], b["requirements"][0]["obligations"])


class TestMatrixRow02ZeroHitl(unittest.TestCase):
    def test_static_hitl_audits(self) -> None:
        rows = run_context_audits(_PKG)
        hitl = [r for r in rows if "hitl" in r["name"] or "prompts" in r["name"]]
        self.assertTrue(all(r["ok"] for r in hitl), json.dumps(hitl, indent=2))


class TestMatrixRow03MakerChecker(unittest.TestCase):
    def test_same_session_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            h.action_dispatched(
                {"claim_id": "c1", "contract_ref": "wc-1", "maker_session_id": "sess-a"},
                actor="maker",
            )
            bad = h.record_evidence(
                {
                    "schema": "eglk.evidence_bundle",
                    "evidence_id": "e1",
                    "contract_ref": "wc-1",
                    "checker_session_id": "sess-a",
                    "world_revision": 0,
                    "verdicts": [],
                },
                actor="checker",
            )
            self.assertFalse(bad.ok)
            store.release_lease(holder="t")
            store.close()


class TestMatrixRow04GateTruthBlind(unittest.TestCase):
    def test_gate_module_has_no_eval_imports(self) -> None:
        gate_path = _PKG / "domain" / "kernel" / "gate.py"
        tree = ast.parse(gate_path.read_text(encoding="utf-8"))
        banned = ("eval_runner", "wa_hard", "WebArena", "scorer")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for b in banned:
                        self.assertNotIn(b, alias.name)
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for b in banned:
                    self.assertNotIn(b, mod)

    def test_gate_schema_no_float_completion(self) -> None:
        data = json.loads((_SCHEMA_DIR / "gate_decision.schema.json").read_text(encoding="utf-8"))
        props = data.get("properties") or {}
        self.assertNotIn("perception_gap", props)
        self.assertNotIn("audit_progress", props)


class TestMatrixRow05AbortOnlyExhaustion(unittest.TestCase):
    def test_abort_reasons_closed_and_audit(self) -> None:
        schema = json.loads((_SCHEMA_DIR / "gate_decision.schema.json").read_text(encoding="utf-8"))
        then = (schema.get("then") or {}).get("properties") or {}
        enum = set(then.get("reason", {}).get("enum") or [])
        self.assertEqual(enum, set(ABORT_REASONS))
        self.assertGreaterEqual(len(ABORT_REASONS), 9)

        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            gd = h._append(
                "GateDecided",
                {"decision": "abort", "reason": "cognitive_budget", "node_id": "root", "contract_ref": "wc"},
            )
            h._append("RunAborted", {"reason": "cognitive_budget"}, causation_id=gd.event_id)
            ok, detail = audit_run_aborted_chain(store.read_all())
            self.assertTrue(ok, detail)
            store.release_lease(holder="t")
            store.close()


class TestMatrixRow06ContextAsCode(unittest.TestCase):
    def test_skills_present(self) -> None:
        skills = _PKG / "domain" / "memory" / "skills"
        for name in ("maker.md", "checker.md", "governor.md", "explorer.md", "verifier.md", "refiner.md"):
            self.assertTrue((skills / name).is_file(), name)


class TestMatrixRow07EventSsot(unittest.TestCase):
    def test_replay_equivalence_after_wipe(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            (workdir / ".goal.md").write_text("# t\n\n- [ ] t\n", encoding="utf-8")
            from eglk_harness.domain.kernel.run_engine import RunEngine

            engine = RunEngine(workdir=workdir, goal_id="g-replay", goal_title="t", done_criteria=["t"])
            engine.bootstrap()
            loop = engine.loop_dir
            before = rebuild_from_events(loop)
            proj_dir = loop / "projections"
            if proj_dir.is_dir():
                import shutil

                shutil.rmtree(proj_dir)
            replay_workdir(workdir, "g-replay")
            after = rebuild_from_events(loop)
            self.assertEqual([], projection_diff(before["run"], after["run"]))
            engine.close()


class TestMatrixRow08ModelEconomics(unittest.TestCase):
    def test_quota_by_role_monotonic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            h.run_created(goal_id="g", memory_digest="sha256:" + "a" * 64, cognitive_tokens_max=100, repairs_max=8)
            for role in ("maker", "checker", "governor", "explorer", "verifier", "refiner"):
                h.quota_updated(role=role, tokens_delta=5)
            proj = h.projection()
            for role in ("maker", "checker", "governor", "explorer", "verifier", "refiner"):
                self.assertGreaterEqual(proj.cognitive_tokens_by_role.get(role, 0), 5)
            store.release_lease(holder="t")
            store.close()


class TestMatrixRow09DynamicTree(unittest.TestCase):
    def test_merge_validator_present(self) -> None:
        ok, _ = validate_merge_obligations(
            source_obligation_sets=[["ob-1"], ["ob-2"]],
            merged_obligation_refs=["ob-1", "ob-2"],
            satisfied_obligation_ids=["ob-1"],
        )
        self.assertTrue(ok)


class TestMatrixRow10FreshSessions(unittest.TestCase):
    def test_session_reuse_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            h.action_dispatched(
                {"claim_id": "c1", "contract_ref": "wc-1", "maker_session_id": "sess-a"},
                actor="maker",
            )
            bad = h.action_dispatched(
                {"claim_id": "c2", "contract_ref": "wc-2", "maker_session_id": "sess-a"},
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


class TestMatrixRow11CheckerIntegrity(unittest.TestCase):
    def test_integrity_blocks_admit(self) -> None:
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
        }
        evidence = {
            "schema": "eglk.evidence_bundle",
            "evidence_id": "e1",
            "contract_ref": "wc-1",
            "checker_session_id": "c1",
            "world_revision": 0,
            "verdicts": [{"obligation_id": "ob-1", "status": "satisfied", "attestations": [], "gaps": []}],
            "integrity_violation": True,
        }
        d = decide(contract, claim, evidence)
        self.assertNotEqual(d.decision, "admit")


class TestMatrixRow12ControlledTransactions(unittest.TestCase):
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
            ok, detail = audit_transaction_sequences(store.read_all())
            self.assertTrue(ok, detail)
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
