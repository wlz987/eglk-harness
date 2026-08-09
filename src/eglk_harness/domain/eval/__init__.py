"""eval domain package — kernel adjacency; suite connectors live in EGLK_EVAL_ROOT/lib/."""

from __future__ import annotations

from eglk_harness.domain.eval.loader import (
    DEFAULT_EVAL_SUITES,
    discover_suites,
    eval_suite_choices,
    load_env_probes_module,
    load_suite_module,
)

EVAL_SUITES = DEFAULT_EVAL_SUITES
