"""Σ lifecycle SSOT + single-tick multi-advisor Quota + irreversible admit E2E."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from eglk_harness.app import RunRequest, _run_loop
from eglk_harness.domain.capability import CapabilityBroker, CapabilityEntry, CapabilityManifest
from eglk_harness.domain.event_store import open_store
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.goal_parse import goal_id, read_goal_text
from eglk_harness.domain.kernel.transaction_audit import audit_transaction_sequences
from eglk_harness.domain.memory import sigma
from eglk_harness.domain.memory.lifecycle import load_active_records
from eglk_harness.domain.product.init_project import init_project


def _repair_gate(handler: Any, *, contract_id: str = "wc-repair") -> None:
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


class TestSigmaLifecycleActiveDir(unittest.TestCase):
    def test_load_active_uses_lifecycle_dir_not_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            active_dir = paths.memory_lifecycle_dirs(workdir)["active"]
            rec = {
                "schema": "eglk.memory_record",
                "id": "sigma-hit-test",
                "kind": "hit",
                "text": "lesson",
                "conf": 0.9,
                "lifecycle_status": "active",
            }
            active_dir.mkdir(parents=True, exist_ok=True)
            (active_dir / "sigma-hit-test.json").write_text(
                json.dumps(rec, indent=2) + "\n", encoding="utf-8"
            )
            loaded = sigma.load_active(workdir)
            self.assertEqual(1, len(loaded))
            self.assertEqual("sigma-hit-test", loaded[0]["id"])
            self.assertFalse((_legacy := paths.memory_sigma_dir(workdir) / "active.json").is_file())

    def test_migrates_legacy_active_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            legacy = paths.memory_sigma_dir(workdir) / "active.json"
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text(
                json.dumps([{"id": "legacy-1", "kind": "hit", "text": "old", "conf": 0.8}]),
                encoding="utf-8",
            )
            loaded = sigma.load_active(workdir)
            self.assertEqual(1, len(loaded))
            self.assertEqual("legacy-1", loaded[0]["id"])
            self.assertFalse(legacy.is_file())
            self.assertTrue(
                (paths.memory_lifecycle_dirs(workdir)["active"] / "legacy-1.json").is_file()
            )

    def test_distill_reads_lifecycle_active(self) -> None:
        from eglk_harness.domain.memory import skill_lib

        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            sigma.save_active_record(
                workdir,
                {
                    "id": "sigma-distill-me",
                    "kind": "hit",
                    "text": "reusable pattern for forms",
                    "conf": 0.9,
                    "verifications": 2,
                    "lifecycle_status": "active",
                },
            )
            created = skill_lib.distill_from_sigma(workdir, min_conf=0.8, min_verifications=2)
            self.assertEqual(1, len(created))
            active = load_active_records(workdir)
            self.assertTrue(any(r.get("distilled_into") for r in active))


class TestSingleTickMultiAdvisorQuota(unittest.TestCase):
    def test_one_tick_all_advisor_roles_quota_updated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            paths.goal_path(workdir).write_text(
                "# Hello\n\n## Done criteria\n- [ ] hello.txt exists\n",
                encoding="utf-8",
            )
            text = read_goal_text(workdir)
            gid = goal_id(text)
            loop_dir = paths.ensure_loop_layout(workdir, gid)

            from eglk_harness.domain.kernel.event_runtime import RunEventContext

            ctx = RunEventContext(workdir, gid)
            ctx.acquire()
            ctx.bootstrap_if_needed(goal_title="Hello", done_criteria=["hello.txt exists"])
            ctx.handler.node_ready("root")
            _repair_gate(ctx.handler, contract_id="wc-r1")
            _repair_gate(ctx.handler, contract_id="wc-r2")
            ctx.export_projections()
            ctx.release()

            cand = loop_dir / "candidates"
            cand.mkdir(parents=True, exist_ok=True)
            for i in range(21):
                (cand / f"overflow_{i:03d}.json").write_text(
                    json.dumps({"id": f"overflow-{i}"}) + "\n", encoding="utf-8"
                )

            (loop_dir / "ticks.jsonl").write_text(
                json.dumps(
                    {"tick": 0, "decision": "repair", "reason": "integrity_violation"}
                )
                + "\n",
                encoding="utf-8",
            )

            asyncio.run(
                _run_loop(
                    RunRequest(
                        workdir=workdir,
                        agent="mock",
                        fake_mode="admit",
                        max_ticks=1,
                        compile="off",
                        swarm="1",
                        tick=1,
                    )
                )
            )

            store = open_store(loop_dir)
            roles: set[str] = set()
            for ev in store.read_all():
                if ev.type != "QuotaUpdated":
                    continue
                by_role = (ev.payload or {}).get("cognitive_tokens_by_role") or {}
                if isinstance(by_role, dict):
                    roles.update(str(k) for k in by_role)
            store.close()

            for role in (
                "governor",
                "explorer",
                "verifier",
                "candidate_selector",
                "maker",
                "checker",
            ):
                self.assertIn(role, roles, f"missing QuotaUpdated role={role}")


class TestIrreversibleAdmitE2E(unittest.TestCase):
    def _irreversible_broker(self) -> CapabilityBroker:
        manifest = CapabilityManifest(
            schema="eglk.capability_manifest",
            manifest_id="test-irreversible-admit",
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

    def test_admit_commits_irreversible_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            from eglk_harness.domain.kernel.event_runtime import RunEventContext

            ctx = RunEventContext(workdir, "g-irrev-admit")
            ctx.broker = self._irreversible_broker()
            ctx.handler.broker = ctx.broker
            ctx.acquire()
            ctx.bootstrap_if_needed(goal_title="irrev", done_criteria=["done"])
            ctx.handler.node_ready("root")
            contract = ctx.assemble_contract_for_node("root")
            policy = dict(contract.get("transaction_policy") or {})
            policy["side_effect_class_ceiling"] = [
                "read_only",
                "reversible",
                "irreversible",
            ]
            contract["transaction_policy"] = policy
            ctx.contract_assembled(contract)
            claim = {
                "schema": "eglk.action_claim",
                "claim_id": "ac-ir-admit",
                "contract_ref": contract["contract_id"],
                "maker_session_id": "m-ir-admit",
                "actions": [
                    {
                        "action_id": "a-ir-admit",
                        "kind": "http_call",
                        "side_effect_class": "irreversible",
                        "target": "api/charge",
                        "idempotency_key": "idem-ir-admit-1",
                    }
                ],
                "alternatives": [{"text": "skip", "status": "reject"}],
                "self_assessment": {"done_progress": 1.0, "confidence": 1.0},
            }
            self.assertTrue(ctx.authorize_maker(claim).ok)
            ctx.dispatch_claim(claim, actor="maker")
            tx = ctx.apply_claim_to_tx(claim)
            world_rev = ctx.env.observe_revision(tx)
            evidence = {
                "schema": "eglk.evidence_bundle",
                "evidence_id": "ev-ir-admit",
                "contract_ref": contract["contract_id"],
                "checker_session_id": "c-ir-admit",
                "world_revision": world_rev,
                "verdicts": [
                    {
                        "obligation_id": "ob-1",
                        "status": "satisfied",
                        "attestations": [
                            {
                                "method": "custom_attestation",
                                "world_revision": world_rev,
                                "digest": "sha256:" + "a" * 64,
                                "observer": "c-ir-admit",
                                "raw_ref": "api/charge",
                                "watch_set": ["api/charge"],
                            }
                        ],
                        "gaps": [],
                    }
                ],
            }
            ctx.record_evidence(evidence, actor="checker")
            gd = ctx.gate_decide(claim=claim, evidence=evidence)
            decision = str((gd.events[0].payload or {}).get("decision") or "")
            self.assertEqual(decision, "admit")
            ctx.finalize_transaction_after_gate(decision)
            types = [e.type for e in ctx.store.read_all()]
            self.assertIn("TransactionCommitted", types)
            passed, detail = audit_transaction_sequences(ctx.store.read_all())
            self.assertTrue(passed, detail)
            ctx.release()


if __name__ == "__main__":
    unittest.main()
