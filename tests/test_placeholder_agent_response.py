"""Boundary rejects schema-placeholder JSON deliverables with hint sidecar."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.runtime.boundary_verify import is_valid_must_exist_file, verify_boundary
from eglk_harness.domain.runtime.mechanical_evidence import synthesize_mechanical_evidence


def _write_hint(workdir: Path, hint: dict) -> None:
    (workdir / ".eglk-harness").mkdir(parents=True, exist_ok=True)
    path = workdir / ".eglk-harness" / "deliverable_hint.json"
    path.write_text(json.dumps(hint) + "\n", encoding="utf-8")


class PlaceholderAgentResponseTests(unittest.TestCase):
    def test_reject_hint_template_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "agent_runs" / "11").mkdir(parents=True)
            _write_hint(
                workdir,
                {
                    "task_type": "RETRIEVE",
                    "placeholder_when": {"task_type": "RETRIEVE", "status": "SUCCESS"},
                    "placeholder_keys": ["retrieved_data"],
                    "example_success": {
                        "task_type": "RETRIEVE",
                        "status": "SUCCESS",
                        "retrieved_data": [0],
                        "error_details": None,
                        "_placeholder": True,
                    },
                },
            )
            resp = workdir / "agent_runs" / "11" / "agent_response.json"
            resp.write_text(
                json.dumps(
                    {
                        "task_type": "RETRIEVE",
                        "status": "SUCCESS",
                        "retrieved_data": [0],
                        "error_details": None,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertFalse(
                is_valid_must_exist_file(resp, rel="agent_runs/11/agent_response.json")
            )
            gaps = verify_boundary(
                workdir, ["MUST_EXIST: agent_runs/11/agent_response.json"]
            )
            self.assertTrue(any("placeholder" in g for g in gaps))

    def test_accept_non_template_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "agent_runs" / "11").mkdir(parents=True)
            _write_hint(
                workdir,
                {
                    "task_type": "RETRIEVE",
                    "placeholder_when": {"task_type": "RETRIEVE", "status": "SUCCESS"},
                    "placeholder_keys": ["retrieved_data"],
                    "example_success": {
                        "retrieved_data": [0],
                    },
                },
            )
            resp = workdir / "agent_runs" / "11" / "agent_response.json"
            resp.write_text(
                json.dumps(
                    {
                        "task_type": "RETRIEVE",
                        "status": "SUCCESS",
                        "retrieved_data": [3],
                        "error_details": None,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertTrue(
                is_valid_must_exist_file(resp, rel="agent_runs/11/agent_response.json")
            )

    def test_root_deliverable_hint_path_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "deliverables").mkdir(parents=True)
            hint = {
                "placeholder_when": {"status": "SUCCESS"},
                "placeholder_keys": ["value"],
                "example_success": {"value": "template"},
            }
            (workdir / ".deliverable_hint.json").write_text(
                json.dumps(hint) + "\n", encoding="utf-8"
            )
            path = workdir / "deliverables" / "answer.json"
            path.write_text(json.dumps({"status": "SUCCESS", "value": "template"}) + "\n", encoding="utf-8")
            self.assertFalse(is_valid_must_exist_file(path, rel="deliverables/answer.json"))

    def test_mechanical_evidence_flags_path_ack_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "hello.txt").write_text("ok\n", encoding="utf-8")
            ev = synthesize_mechanical_evidence(
                workdir=workdir,
                claim={"note": "mechanical_claim_from_boundary"},
                contract_ref="wc-1",
                obligation_refs=["ob-1", "ob-2"],
                boundary=["MUST_EXIST: hello.txt"],
                world_revision=0,
                tick=0,
            )
            self.assertIsNotNone(ev)
            assert ev is not None
            self.assertEqual(ev["verdicts"][0]["status"], "unsatisfied")
            self.assertEqual(ev["verdicts"][1]["status"], "unsatisfied")


if __name__ == "__main__":
    unittest.main()
