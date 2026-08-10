"""Dynamic eval plugin loader — suite connectors live in ``EGLK_EVAL_ROOT/lib/``."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from eglk_harness.domain.eval.paths import default_eval_root

# CLI ``--suite`` name → ``lib/<stem>.py``
_SUITE_MODULE_STEM: dict[str, str] = {
    "osworld_aux": "osworld",
}

# Argparse fallback when ``EGLK_EVAL_ROOT`` unset.
DEFAULT_EVAL_SUITES: frozenset[str] = frozenset(
    {
        "weave_lh",
        "wa_hard",
        "osworld_aux",
        "tb21",
        "scenarios",
    }
)


def resolve_eval_root(eval_root: Path | None = None) -> Path:
    root = Path(eval_root).resolve() if eval_root is not None else default_eval_root()
    if root is None:
        raise FileNotFoundError("EGLK_EVAL_ROOT not set (or pass eval_root=...)")
    return root


def suite_module_stem(suite: str) -> str:
    return _SUITE_MODULE_STEM.get(suite, suite)


def _load_plugin(path: Path, module_name: str) -> ModuleType:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"eval plugin not found: {path}")
    cached = sys.modules.get(module_name)
    if cached is not None and getattr(cached, "__file__", None) == str(path):
        return cached
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load eval plugin: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_suite_module(suite: str, eval_root: Path | None = None) -> ModuleType:
    root = resolve_eval_root(eval_root)
    stem = suite_module_stem(suite)
    return _load_plugin(root / "lib" / f"{stem}.py", f"eglk_eval.{stem}")


def load_env_probes_module(eval_root: Path | None = None) -> ModuleType:
    root = resolve_eval_root(eval_root)
    return _load_plugin(root / "lib" / "eval_env_probes.py", "eglk_eval.env_probes")


def discover_suites(eval_root: Path | None = None) -> frozenset[str]:
    root = resolve_eval_root(eval_root)
    names: set[str] = set()
    lib = root / "lib"
    if lib.is_dir():
        for path in sorted(lib.glob("*.py")):
            stem = path.stem
            if stem in {"eval_env_probes", "__init__"} or stem.startswith("_"):
                continue
            if stem == "osworld":
                names.add("osworld_aux")
            else:
                names.add(stem)
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith(".") and (
            (child / "pack.json").is_file() or (child / "pack.example.json").is_file()
        ):
            names.add(child.name)
    return frozenset(names) if names else DEFAULT_EVAL_SUITES


def eval_suite_choices(eval_root: Path | None = None) -> frozenset[str]:
    if eval_root is not None:
        try:
            return discover_suites(eval_root)
        except FileNotFoundError:
            pass
    root = default_eval_root()
    if root is not None:
        try:
            return discover_suites(root)
        except FileNotFoundError:
            pass
    return DEFAULT_EVAL_SUITES
