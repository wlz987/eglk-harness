"""Mechanical checker must not satisfy custom_attestation obligations (B route)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.runtime.mechanical_evidence import (
    has_intent_obligations,
    synthesize_mechanical_evidence,
)


class TestMechanicalEvidenceIntent(unittest.TestCase):
    def test_has_intent_obligations_default_custom(self) -> None:
        self.assertTrue(has_intent_obligations(["ob-1"], {}))

    def test_custom_attestation_never_mechanical_satisfied(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            (workdir / "out").mkdir()
            (workdir / "out" / "report.json").write_text("{}", encoding="utf-8")
            boundary = ["MUST_EXIST: out/report.json"]
            mech = synthesize_mechanical_evidence(
                workdir=workdir,
                claim={"note": "mechanical_claim"},
                contract_ref="wc-test",
                obligation_refs=["ob-1"],
                boundary=boundary,
                world_revision=0,
                tick=0,
                obligation_verification_types={"ob-1": "custom_attestation"},
            )
            self.assertIsNotNone(mech)
            verdict = mech["verdicts"][0]
            self.assertEqual(verdict["status"], "unsatisfied")
            self.assertTrue(
                any("intent obligation" in g for g in verdict.get("gaps") or [])
            )

    def test_file_exists_obligation_can_satisfy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            (workdir / "out").mkdir()
            (workdir / "out" / "report.json").write_text('{"ok": true}', encoding="utf-8")
            boundary = ["MUST_EXIST: out/report.json"]
            mech = synthesize_mechanical_evidence(
                workdir=workdir,
                claim={
                    "actions": [
                        {
                            "kind": "file_write",
                            "payload": {"path": "out/report.json", "ok": True},
                        }
                    ]
                },
                contract_ref="wc-test",
                obligation_refs=["ob-1"],
                boundary=boundary,
                world_revision=0,
                tick=0,
                obligation_verification_types={"ob-1": "file_exists"},
            )
            self.assertIsNotNone(mech)
            self.assertEqual(mech["verdicts"][0]["status"], "satisfied")


if __name__ == "__main__":
    unittest.main()
