"""Mock E2E: split goal → two child admits → RunSucceeded."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from eglk_harness.app import RunRequest, _run_loop
from eglk_harness.domain.event_store import open_store
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.goal_parse import goal_id, read_goal_text
from eglk_harness.domain.kernel.event_runtime import RunEventContext
from eglk_harness.domain.product.init_project import init_project


def _repair_gate(handler, *, contract_id: str = "wc-repair") -> None:
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


class TestMultiLeafMockE2E(unittest.TestCase):
    def test_split_two_leaves_both_admit_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            paths.goal_path(workdir).write_text(
                "# Dual deliverable\n\n## Done criteria\n"
                "- [ ] part_a.txt exists\n"
                "- [ ] part_b.txt exists\n",
                encoding="utf-8",
            )
            text = read_goal_text(workdir)
            gid = goal_id(text)
            loop_dir = paths.ensure_loop_layout(workdir, gid)

            ctx = RunEventContext(workdir, gid)
            ctx.acquire()
            ctx.bootstrap_if_needed(
                goal_title="Dual deliverable",
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
                        max_ticks=16,
                        compile="off",
                        swarm="0",
                    )
                )
            )

            self.assertTrue((workdir / "part_a.txt").is_file())
            self.assertTrue((workdir / "part_b.txt").is_file())
            store = open_store(loop_dir)
            types = [e.type for e in store.read_all()]
            store.close()
            self.assertIn("SplitCommitted", types)
            self.assertIn("RunSucceeded", types)
            self.assertTrue(result.get("outcome", {}).get("ok"))


if __name__ == "__main__":
    unittest.main()
