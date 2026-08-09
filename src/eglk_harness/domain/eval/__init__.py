"""eval domain package."""

from __future__ import annotations

# Keep in sync with CLI ``--suite`` choices and design/kernel/packaging.md
EVAL_SUITES: frozenset[str] = frozenset(
    {
        "weave_thin",
        "weave_lh",
        "wa_hard",
        "osworld_aux",
        "scenarios",
    }
)
