"""defect_suspected on derived obligations → ObligationAmendmentProposed."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.advisors import build_mechanical_split_candidate
from eglk_harness.domain.kernel.command_handler import CommandHandler


class TestDefectSuspectedAmendment(unittest.TestCase):
    def test_record_defect_suspected_proposes_amendment(self) -> None:
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
                            "statement": "parent deliverable",
                            "verification_type": "custom_attestation",
                            "status": "open",
                            "origin": "root",
                        }
                    ],
                }
            )
            h.node_ready("root")
            mech = build_mechanical_split_candidate(h.projection(), "root", step=0)
            self.assertIsNotNone(mech)
            h.commit_split(mech, actor="governor")
            derived_id = None
            for ob in mech.get("opened_obligations") or []:
                if str(ob.get("origin") or "") == "derived":
                    derived_id = str(ob.get("id"))
                    break
            if derived_id is None:
                for ch in mech.get("children") or []:
                    refs = ch.get("obligation_refs") or []
                    if refs:
                        derived_id = str(refs[0])
                        break
            self.assertIsNotNone(derived_id)
            evidence = {
                "schema": "eglk.evidence_bundle",
                "evidence_id": "ev-1",
                "contract_ref": "wc-1",
                "checker_session_id": "c-1",
                "world_revision": 1,
                "verdicts": [
                    {
                        "obligation_id": derived_id,
                        "status": "unsatisfied",
                        "attestations": [],
                        "gaps": ["statement impossible"],
                        "defect_suspected": True,
                    }
                ],
            }
            results = h.record_defect_suspected_amendments(evidence, actor="governor")
            self.assertTrue(results)
            types = [e.type for e in store.read_all()]
            self.assertIn("ObligationAmendmentProposed", types)
            self.assertIn("ObligationAmended", types)
            ob = h.projection().obligations[derived_id]
            self.assertIn("[refined:", ob.statement)
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
