"""Regression: claim sanitize, premature closure, capability-denied advance."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.capability import CapabilityBroker, default_local_fs_manifest
from eglk_harness.domain.event_store import open_store
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.event_runtime import RunEventContext
from eglk_harness.domain.kernel.reducer import NodeState, empty_projection, reduce_events
from eglk_harness.domain.runtime.claim_sanitize import (
    actions_requiring_broker,
    sanitize_claim_for_apply,
)


class ClaimSanitizeTests(unittest.TestCase):
    def test_strips_mcp_session_keeps_file_write(self) -> None:
        claim = {
            "actions": [
                {
                    "action_id": "a1",
                    "kind": "file_write",
                    "side_effect_class": "reversible",
                    "target": "agent_runs/11/agent_response.json",
                    "payload": {"retrieved_data": [6]},
                },
                {
                    "action_id": "a2",
                    "kind": "mcp_session",
                    "side_effect_class": "reversible",
                    "target": "wa-browser",
                },
            ]
        }
        clean = sanitize_claim_for_apply(claim)
        kinds = [a["kind"] for a in clean["actions"]]
        self.assertEqual(kinds, ["file_write"])
        broker_acts = actions_requiring_broker(clean["actions"])
        self.assertEqual(len(broker_acts), 1)
        broker = CapabilityBroker(default_local_fs_manifest())
        d = broker.authorize_action(role="maker", action=broker_acts[0], ceiling=["reversible"])
        self.assertTrue(d.allowed, d.reason)

    def test_workdir_relative_file_write_authorizes(self) -> None:
        acts = actions_requiring_broker(
            [
                {
                    "action_id": "w1",
                    "kind": "file_write",
                    "side_effect_class": "reversible",
                    "target": "workdir/hello.txt",
                    "payload": {"path": "hello.txt", "content": "ok\n"},
                }
            ]
        )
        self.assertEqual(acts[0]["target"], "workdir/hello.txt")
        broker = CapabilityBroker(default_local_fs_manifest())
        d = broker.authorize_action(role="maker", action=acts[0], ceiling=["reversible"])
        self.assertTrue(d.allowed, d.reason)


class ClosureNeededTests(unittest.TestCase):
    def test_in_progress_does_not_need_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / ".goal.md").write_text("# g\n", encoding="utf-8")
            ctx = RunEventContext(workdir, "g1")
            # Minimal projection via handler after bootstrap-ish empty store
            ctx.handler.acquire()
            try:
                # Manually seed projection by appending events
                ctx.handler.run_created(
                    goal_id="g1",
                    memory_digest="sha256:" + "0" * 64,
                    cognitive_tokens_max=64000,
                    repairs_max=8,
                )
                ctx.handler.goal_compiled(
                    {
                        "goal_spec_ref": "x",
                        "source_digest": "sha256:" + "1" * 64,
                        "root_node_id": "root",
                        "title": "root",
                        "obligation_refs": ["ob-1"],
                        "obligations": [
                            {
                                "id": "ob-1",
                                "requirement_id": "r1",
                                "statement": "s",
                                "verification_type": "custom_attestation",
                                "origin": "root",
                            }
                        ],
                    }
                )
                ctx.handler.node_ready("root")
                contract = ctx.assemble_contract_for_node("root")
                ctx.contract_assembled(contract)
                # root now in_progress — must NOT trigger closure
                self.assertFalse(ctx.closure_needed())
                # reopen → ready → still not closure (work remains)
                ctx.handler.reopen_stranded_in_progress_nodes()
                self.assertFalse(ctx.closure_needed())
                self.assertEqual(ctx.select_node_id(), "root")
            finally:
                ctx.release()
                ctx.close()


class CapabilityDeniedAdvanceTests(unittest.TestCase):
    def test_record_apply_denied_emits_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            loop = Path(tmp) / "loop"
            loop.mkdir()
            store = open_store(loop)
            handler = CommandHandler(store, broker=CapabilityBroker(default_local_fs_manifest()))
            handler.acquire()
            try:
                handler.run_created(
                    goal_id="g",
                    memory_digest="sha256:" + "0" * 64,
                    cognitive_tokens_max=64000,
                    repairs_max=8,
                )
                handler.goal_compiled(
                    {
                        "goal_spec_ref": "x",
                        "source_digest": "sha256:" + "1" * 64,
                        "root_node_id": "root",
                        "title": "root",
                        "obligation_refs": ["ob-1"],
                        "obligations": [
                            {
                                "id": "ob-1",
                                "requirement_id": "r1",
                                "statement": "s",
                                "verification_type": "custom_attestation",
                                "origin": "root",
                            }
                        ],
                    }
                )
                handler.node_ready("root")
                res = handler.record_apply_denied(
                    contract={
                        "contract_id": "wc-1",
                        "node_id": "root",
                        "obligation_refs": ["ob-1"],
                    }
                )
                self.assertTrue(res.ok)
                types = [e.type for e in res.events]
                self.assertIn("GateDecided", types)
                gd = next(e for e in res.events if e.type == "GateDecided")
                self.assertEqual(gd.payload.get("decision"), "repair")
                self.assertEqual(gd.payload.get("reason"), "capability_denied")
                proj = handler.projection()
                self.assertEqual(proj.nodes["root"].status, "ready")
                self.assertEqual(proj.repairs_used, 1)
                # Exhaustion must use the same key reducer recorded (ob-1:capability_denied).
                for _ in range(7):
                    res2 = handler.record_apply_denied(
                        contract={
                            "contract_id": "wc-1",
                            "node_id": "root",
                            "obligation_refs": ["ob-1"],
                        }
                    )
                    self.assertTrue(res2.ok)
                res3 = handler.record_apply_denied(
                    contract={
                        "contract_id": "wc-1",
                        "node_id": "root",
                        "obligation_refs": ["ob-1"],
                    }
                )
                gd3 = next(e for e in res3.events if e.type == "GateDecided")
                self.assertEqual(gd3.payload.get("decision"), "abort")
                self.assertEqual(gd3.payload.get("reason"), "capability_denied_exhausted")
            finally:
                handler.release()
                store.close()


if __name__ == "__main__":
    unittest.main()
