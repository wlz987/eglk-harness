"""process_coverage sidecar structural validation (C route)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.runtime.boundary_verify import verify_boundary
from eglk_harness.domain.runtime.process_coverage import (
    normalize_process_coverage,
    validate_process_coverage,
)


class TestProcessCoverageSchema(unittest.TestCase):
    def test_normalize_pagination_alias(self) -> None:
        out = normalize_process_coverage({"pagination_exhausted": True, "pages_scanned": 2})
        self.assertTrue(out["enumeration_exhausted"])
        self.assertTrue(out["pagination_exhausted"])

    def test_validate_requires_exhaustion_flag(self) -> None:
        violations = validate_process_coverage({"pages_scanned": 1})
        self.assertTrue(any("enumeration_exhausted" in v for v in violations))

    def test_boundary_verify_process_coverage_structure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            rel = "agent_runs/t1/coverage_note.json"
            path = workdir / rel
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"pages_scanned": 1}), encoding="utf-8")
            violations = verify_boundary(workdir, [f"MUST_EXIST: {rel}"])
            self.assertTrue(any("enumeration_exhausted" in v for v in violations))

    def test_valid_coverage_passes_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            rel = "agent_runs/t1/process_coverage.json"
            path = workdir / rel
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "pages_scanned": 3,
                        "enumeration_exhausted": True,
                        "sources": ["https://example/admin"],
                        "note": "scanned grid",
                    }
                ),
                encoding="utf-8",
            )
            violations = verify_boundary(workdir, [f"MUST_EXIST: {rel}"])
            self.assertFalse(violations)


if __name__ == "__main__":
    unittest.main()
