"""Oracle guard env → Checker prompt block."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from eglk_harness.domain.runtime.oracle_guard import format_oracle_guard_block, oracle_forbidden_prefixes


class OracleGuardTests(unittest.TestCase):
    def test_empty_when_unset(self) -> None:
        env = os.environ.copy()
        env.pop("EGLK_ORACLE_FORBIDDEN_PREFIXES", None)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(oracle_forbidden_prefixes(), [])
            self.assertEqual(format_oracle_guard_block(), "")

    def test_formats_block(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"EGLK_ORACLE_FORBIDDEN_PREFIXES": "/tmp/scorer-only,/tmp/export.json"},
            clear=False,
        ):
            prefixes = oracle_forbidden_prefixes()
            self.assertEqual(len(prefixes), 2)
            block = format_oracle_guard_block()
            self.assertIn("[ORACLE_GUARD]", block)
            self.assertIn("/tmp/scorer-only", block)


if __name__ == "__main__":
    unittest.main()
