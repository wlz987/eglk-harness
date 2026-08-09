"""Cross-run Σ promotion, governor split E2E, memory boundary enforcement."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.app import RunRequest, _run_loop
from eglk_harness.domain.event_store import open_store
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.goal_parse import goal_id, read_goal_text
from eglk_harness.domain.memory.lifecycle import (
    digest_active_snapshot,
    load_active_records,
    promote,
    write_candidate,
)
from eglk_harness.domain.memory.memory_policy import manifest_memory_fields
from eglk_harness.domain.memory.memory_promotion import (
    namespace_allows_promote,
    run_cross_run_promotion,
)
from eglk_harness.domain.product.init_project import init_project
from eglk_harness.domain.product.manifest import build_manifest


def _repair_gate(handler: CommandHandler, *, contract_id: str = "wc-repair") -> None:
    contract = {
        "schema": "eglk.work_contract",
        "contract_id": contract_id,
        "node_id": "root",
        "obligation_refs": ["ob-1"],
        "boundary": {"allowed_scope": ["workdir/**"], "forbidden_actions": []},
        "transaction_policy": {"side_effect_class_ceiling": ["reversible"]},
    }
    claim = {
        "schema": "eglk.action_claim",
        "claim_id": f"ac-{contract_id}",
        "contract_ref": contract_id,
        "maker_session_id": f"m-{contract_id}",
        "actions": [],
        "alternatives": [{"text": "skip", "status": "reject"}],
        "self_assessment": {"done_progress": 0.5, "confidence": 0.5},
    }
    evidence = {
        "schema": "eglk.evidence_bundle",
        "evidence_id": f"ev-{contract_id}",
        "contract_ref": contract_id,
        "checker_session_id": f"c-{contract_id}",
        "world_revision": 1,
        "verdicts": [
            {
                "obligation_id": "ob-1",
                "status": "unsatisfied",
                "attestations": [],
                "gaps": ["incomplete"],
            }
        ],
    }
    handler.gate_decide(contract=contract, claim=claim, evidence=evidence)


class TestCrossRunMemoryPromotion(unittest.TestCase):
    def test_two_runs_promote_candidate_to_active(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            from eglk_harness.domain.event_store import EventStore

            store = EventStore(workdir / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)

            rec = write_candidate(
                workdir,
                kind="sigma",
                cond="pattern",
                wrong="w",
                correct="reusable lesson",
                conf=0.9,
                namespace="campaign-a",
                origin_goal_id="goal-one",
                origin_run_id="run-goal-one-seq1",
                handler=h,
            )
            rid = str(rec["id"])

            cross1 = run_cross_run_promotion(
                workdir,
                goal_id="goal-two",
                origin_run_id="run-goal-two-seq10",
                handler=h,
                workdir_namespace="campaign-a",
            )
            self.assertGreaterEqual(cross1["quarantined"], 1)

            cross2 = run_cross_run_promotion(
                workdir,
                goal_id="goal-three",
                origin_run_id="run-goal-three-seq20",
                handler=h,
                workdir_namespace="campaign-a",
            )
            self.assertGreaterEqual(cross2["verification_bumps"], 1)
            self.assertGreaterEqual(cross2["promoted_verified"], 1)
            self.assertGreaterEqual(cross2["promoted_active"], 1)

            active = load_active_records(workdir)
            self.assertTrue(any(r.get("id") == rid for r in active))
            promoted = [e for e in store.read_all() if e.type == "MemoryPromoted"]
            transitions = {
                (str((e.payload or {}).get("from_status")), str((e.payload or {}).get("to_status")))
                for e in promoted
            }
            self.assertIn(("verified", "active"), transitions)
            store.release_lease(holder="t")
            store.close()

    def test_namespace_blocks_cross_namespace_active(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            rec = write_candidate(
                workdir,
                kind="sigma",
                cond="c",
                wrong="w",
                correct="r",
                conf=0.95,
                namespace="other-campaign",
                origin_goal_id="g1",
                origin_run_id="run-g1-seq1",
            )
            rid = str(rec["id"])
            dirs = paths.memory_lifecycle_dirs(workdir)
            # Force verified state with enough verifications
            from eglk_harness.domain.memory.lifecycle import bump_verification, quarantine_candidates

            quarantine_candidates(workdir)
            bump_verification(workdir, rid)
            bump_verification(workdir, rid)
            promote(workdir, rid, to_status="verified")
            data = json.loads((dirs["verified"] / f"{rid}.json").read_text(encoding="utf-8"))
            prov = dict(data.get("provenance") or {})
            prov["reviewed_goal_ids"] = ["g1", "g2"]
            data["provenance"] = prov
            (dirs["verified"] / f"{rid}.json").write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )
            self.assertFalse(
                namespace_allows_promote(data, workdir_namespace="campaign-a")
            )
            n = run_cross_run_promotion(
                workdir,
                goal_id="g3",
                origin_run_id="run-g3-seq3",
                workdir_namespace="campaign-a",
            )
            self.assertEqual(0, n["promoted_active"])
            self.assertFalse((dirs["active"] / f"{rid}.json").is_file())


class TestTtlExpiration(unittest.TestCase):
    def test_ttl_moves_to_deprecated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            from eglk_harness.domain.event_store import EventStore
            from eglk_harness.domain.memory.lifecycle import expire_ttl_records, write_candidate

            store = EventStore(workdir / "events.db")
            store.acquire_lease(holder="t")
            h = __import__(
                "eglk_harness.domain.kernel.command_handler", fromlist=["CommandHandler"]
            ).CommandHandler(store)
            rec = write_candidate(
                workdir,
                kind="sigma",
                cond="c",
                wrong="w",
                correct="r",
                conf=0.5,
                namespace="n",
                origin_goal_id="g1",
                origin_run_id="run-g1-seq1",
                handler=h,
            )
            rid = str(rec["id"])
            from eglk_harness.domain.memory.lifecycle import quarantine_candidates, promote

            quarantine_candidates(workdir, handler=h)
            bump = __import__(
                "eglk_harness.domain.memory.lifecycle", fromlist=["bump_verification"]
            ).bump_verification
            bump(workdir, rid)
            promote(workdir, rid, to_status="verified", handler=h)
            verified_path = paths.memory_lifecycle_dirs(workdir)["verified"] / f"{rid}.json"
            data = json.loads(verified_path.read_text(encoding="utf-8"))
            data["ttl_at"] = "2000-01-01T00:00:00Z"
            verified_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            n = expire_ttl_records(workdir, handler=h)
            self.assertEqual(1, n)
            dep = paths.memory_lifecycle_dirs(workdir)["deprecated"] / f"{rid}.json"
            self.assertTrue(dep.is_file())
            deprecated = [e for e in store.read_all() if e.type == "MemoryDeprecated"]
            self.assertGreaterEqual(len(deprecated), 1)
            store.release_lease(holder="t")
            store.close()


class TestContextCompressSkill(unittest.TestCase):
    def test_skill_ref_loadable(self) -> None:
        from eglk_harness.domain.memory.context_compress import skill_ref

        meta = skill_ref()
        self.assertEqual("context_compress", meta.get("name"))


class TestSensitiveMemoryBoundaries(unittest.TestCase):
    def test_sensitive_excluded_from_active_digest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            active_dir = paths.memory_lifecycle_dirs(workdir)["active"]
            active_dir.mkdir(parents=True, exist_ok=True)
            (active_dir / "public.json").write_text(
                json.dumps({"id": "pub", "kind": "hit", "text": "ok", "conf": 0.9, "sensitive": False})
                + "\n",
                encoding="utf-8",
            )
            (active_dir / "secret.json").write_text(
                json.dumps(
                    {
                        "id": "secret",
                        "kind": "hit",
                        "text": "hidden",
                        "conf": 0.9,
                        "sensitive": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            digest = digest_active_snapshot(workdir)
            self.assertNotIn("secret", digest)
            records = load_active_records(workdir)
            self.assertEqual(1, len(records))
            self.assertEqual("pub", records[0]["id"])

    def test_sensitive_cannot_promote_to_active(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            rec = write_candidate(
                workdir,
                kind="sigma",
                cond="c",
                wrong="w",
                correct="r",
                conf=0.95,
                namespace="n",
                origin_goal_id="g1",
                origin_run_id="run-g1-seq1",
                sensitive=True,
            )
            rid = str(rec["id"])
            from eglk_harness.domain.memory.lifecycle import bump_verification, quarantine_candidates

            quarantine_candidates(workdir)
            bump_verification(workdir, rid)
            bump_verification(workdir, rid)
            promote(workdir, rid, to_status="verified")
            with self.assertRaises(ValueError):
                promote(workdir, rid, to_status="active", by_run_id="run-g2-seq2")

    def test_manifest_records_memory_sharing_when_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            import os

            os.environ["EGLK_EVAL_FREEZE_MEMORY"] = "1"
            try:
                fields = manifest_memory_fields(workdir)
                self.assertEqual("frozen_active", fields.get("memory_sharing"))
                doc = build_manifest(
                    run_id="r1",
                    workdir=workdir,
                    goal_id="g",
                    agent="mock",
                    extra={"run_status": "succeeded"},
                )
                self.assertEqual(
                    "frozen_active",
                    (doc.get("_diagnostics") or {}).get("memory_sharing"),
                )
            finally:
                os.environ.pop("EGLK_EVAL_FREEZE_MEMORY", None)


class TestGovernorSplitE2E(unittest.TestCase):
    def test_repair_streak_triggers_split_and_child_admits(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            paths.goal_path(workdir).write_text(
                "# Split goal\n\n## Done criteria\n"
                "- [ ] part_a.txt exists\n"
                "- [ ] part_b.txt exists\n",
                encoding="utf-8",
            )
            text = read_goal_text(workdir)
            gid = goal_id(text)
            loop_dir = paths.ensure_loop_layout(workdir, gid)

            from eglk_harness.domain.kernel.event_runtime import RunEventContext

            ctx = RunEventContext(workdir, gid)
            ctx.acquire()
            ctx.bootstrap_if_needed(
                goal_title="Split goal",
                done_criteria=["part_a.txt exists", "part_b.txt exists"],
            )
            ctx.handler.node_ready("root")
            _repair_gate(ctx.handler, contract_id="wc-r1")
            _repair_gate(ctx.handler, contract_id="wc-r2")
            ctx.export_projections()
            ctx.release()

            result = asyncio.run(
                _run_loop(
                    RunRequest(
                        workdir=workdir,
                        agent="mock",
                        fake_mode="admit",
                        max_ticks=12,
                        compile="off",
                        swarm="1",
                        tick=0,
                    )
                )
            )

            store = open_store(loop_dir)
            types = [e.type for e in store.read_all()]
            store.close()
            self.assertIn("SplitCommitted", types)

            self.assertTrue((workdir / "part_a.txt").is_file())
            self.assertTrue((workdir / "part_b.txt").is_file())

            rp = json.loads(
                (loop_dir / "projections" / "run_projection.json").read_text(encoding="utf-8")
            )
            self.assertEqual("succeeded", rp.get("run_status"))
            self.assertTrue(result.get("outcome", {}).get("ok"))


if __name__ == "__main__":
    unittest.main()
