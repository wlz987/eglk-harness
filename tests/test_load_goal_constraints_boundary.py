"""Suite marker boundary lines merge into load_goal_constraints."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.kernel.compile_goal import load_goal_constraints
from eglk_harness.domain.memory.suite_marker import write_marker


class LoadGoalConstraintsSuiteBoundaryTests(unittest.TestCase):
    def test_marker_boundary_merged(self) -> None:
        boundary = [
            "MUST_EXIST: agent_runs/7/agent_response.json (answer JSON)",
            "MUST_EXIST: agent_runs/7/network.har (capture HAR)",
            "USE_MCP: wa-browser",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            write_marker(
                workdir,
                suite="example_suite",
                task_id="7",
                fragments=["example-fragment"],
                boundary=boundary,
            )
            (workdir / ".goal.md").write_text(
                "# Goal\n\n## Constraints\n\n- Preserve `.goal.md`.\n",
                encoding="utf-8",
            )
            lines = load_goal_constraints(workdir)
            self.assertTrue(any("MUST_EXIST: agent_runs/7/agent_response.json" in x for x in lines))
            self.assertTrue(any("USE_MCP: wa-browser" in x for x in lines))


if __name__ == "__main__":
    unittest.main()
