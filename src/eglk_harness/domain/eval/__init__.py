"""eval domain package — suite connectors load from ``EGLK_EVAL_ROOT/lib/``."""

from __future__ import annotations

from eglk_harness.domain.eval.loader import DEFAULT_EVAL_SUITES, eval_suite_choices

EVAL_SUITES: frozenset[str] = DEFAULT_EVAL_SUITES

_IMPORT_SUITE_ALIASES: dict[str, str] = {
    "wa_hard": "wa_hard",
    "osworld": "osworld_aux",
    "weave_lh": "weave_lh",
    "tb21": "tb21",
}


def __getattr__(name: str):
    """Lazy load eval connectors from ``EGLK_EVAL_ROOT`` (backward compat for scripts)."""
    if name in _IMPORT_SUITE_ALIASES:
        from eglk_harness.domain.eval.loader import load_suite_module
        from eglk_harness.domain.eval.paths import default_eval_root

        eval_root = default_eval_root()
        if eval_root is None:
            raise ImportError(
                f"EGLK_EVAL_ROOT required to import eglk_harness.domain.eval.{name}"
            )
        return load_suite_module(_IMPORT_SUITE_ALIASES[name], eval_root)
    if name == "eval_env_probes":
        from eglk_harness.domain.eval.loader import load_env_probes_module
        from eglk_harness.domain.eval.paths import default_eval_root

        eval_root = default_eval_root()
        if eval_root is None:
            raise ImportError(
                "EGLK_EVAL_ROOT required to import eglk_harness.domain.eval.eval_env_probes"
            )
        return load_env_probes_module(eval_root)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
