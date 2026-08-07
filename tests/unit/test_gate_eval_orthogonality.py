"""Orthogonality: Gate must never import eval scorers (truth-blind)."""

from __future__ import annotations

import ast
from pathlib import Path


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_gate_does_not_import_eval() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "eglk_harness"
    gate_files = [
        root / "domain" / "kernel" / "gate.py",
        root / "actors" / "gate" / "__init__.py",
    ]
    forbidden = ("eglk_harness.domain.eval", "domain.eval")
    for path in gate_files:
        assert path.is_file(), path
        mods = _imports_of(path)
        for m in mods:
            assert not any(m == f or m.startswith(f + ".") for f in forbidden), (path, m)


def test_eval_modules_do_not_import_gate() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "eglk_harness" / "domain" / "eval"
    for path in root.glob("*.py"):
        mods = _imports_of(path)
        for m in mods:
            assert "domain.kernel.gate" not in m, (path, m)
            assert not m.endswith(".gate"), (path, m)
