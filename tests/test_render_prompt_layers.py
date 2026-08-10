"""Skill prompt assembly: overlay, fragments, episode layers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.memory.skills import render_prompt
from eglk_harness.domain.memory.suite_marker import write_marker


class RenderPromptLayerTests(unittest.TestCase):
    def test_overlay_and_fragments_injected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            eval_root = workdir / "eval"
            frag_dir = eval_root / "skills" / "fragments"
            frag_dir.mkdir(parents=True)
            (frag_dir / "demo-fragment.md").write_text("DEMO FRAGMENT BODY", encoding="utf-8")
            (eval_root / "skills" / "maker.md").write_text("MAKER OVERLAY LINE", encoding="utf-8")

            write_marker(workdir, suite="demo", fragments=["demo-fragment"])
            import os

            os.environ["EGLK_EVAL_ROOT"] = str(eval_root)

            prompt = render_prompt(
                "maker",
                leaf_block="[LEAF]",
                workdir=workdir,
            )
            self.assertIn("MAKER OVERLAY LINE", prompt)
            self.assertIn("DEMO FRAGMENT BODY", prompt)
            self.assertIn("[LEAF]", prompt)


if __name__ == "__main__":
    unittest.main()
