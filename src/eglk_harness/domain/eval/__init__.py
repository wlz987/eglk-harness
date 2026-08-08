"""eval domain package."""

from __future__ import annotations

# Keep in sync with CLI ``--suite`` choices and eval packaging contract.
EVAL_SUITES: frozenset[str] = frozenset(
    {
        "weave_thin",
        "weave_lh",
        "wa_hard",
        "osworld_aux",
        "tb21",
        "scenarios",
    }
)
