"""Tests for intent_criteria / goal_parse (A route)."""

from __future__ import annotations

import unittest

from eglk_harness.domain.kernel.goal_parse import (
    INTENT_CRITERIA_FALLBACK,
    intent_criteria,
)


class TestIntentCriteria(unittest.TestCase):
    def test_summary_only_no_hello_default(self) -> None:
        text = (
            "# Task\n\n"
            "## Summary\n"
            "List all reviewers who mentioned ear cups in their reviews.\n"
        )
        crit = intent_criteria(text)
        self.assertNotIn("hello.txt exists", crit)
        self.assertTrue(any("ear cups" in c for c in crit))

    def test_checkbox_priority(self) -> None:
        text = (
            "# T\n\n"
            "## Summary\n"
            "Do something broad.\n\n"
            "## Done criteria\n"
            "- [ ] report.json exists\n"
        )
        crit = intent_criteria(text)
        self.assertIn("report.json exists", crit)

    def test_empty_goal_macro_fallback(self) -> None:
        crit = intent_criteria("# Goal\n")
        self.assertEqual(crit, [INTENT_CRITERIA_FALLBACK])

    def test_explicit_hello_when_in_goal(self) -> None:
        text = "# T\n\n- [ ] hello.txt exists\n"
        crit = intent_criteria(text)
        self.assertIn("hello.txt exists", crit)


if __name__ == "__main__":
    unittest.main()
