"""Import orthogonality smoke tests (actors must not import each other)."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "src" / "eglk_harness"
ACTORS = ROOT / "actors"
PROTOCOL = ROOT / "protocol"
DOMAIN = ROOT / "domain"


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_protocol_does_not_import_domain() -> None:
    for path in PROTOCOL.rglob("*.py"):
        for name in _imports_of(path):
            assert not name.startswith("eglk_harness.domain"), path


def test_domain_does_not_import_actors() -> None:
    for path in DOMAIN.rglob("*.py"):
        for name in _imports_of(path):
            assert not name.startswith("eglk_harness.actors"), path


def test_actor_families_do_not_cross_import() -> None:
    families = [p for p in ACTORS.iterdir() if p.is_dir() and p.name != "__pycache__"]
    for fam in families:
        for path in fam.rglob("*.py"):
            for name in _imports_of(path):
                if not name.startswith("eglk_harness.actors."):
                    continue
                # may import eglk_harness.actors (package) or own family
                rest = name.removeprefix("eglk_harness.actors.")
                top = rest.split(".", 1)[0]
                if top in ("",):
                    continue
                assert top == fam.name or top == "__init__", (
                    f"{path} imports foreign actor {name}"
                )


def test_kernel_does_not_import_product_or_eval() -> None:
    kernel = DOMAIN / "kernel"
    forbidden = ("eglk_harness.domain.product", "eglk_harness.domain.eval")
    for path in kernel.rglob("*.py"):
        for name in _imports_of(path):
            assert not any(name == f or name.startswith(f + ".") for f in forbidden), (
                f"{path} imports {name}"
            )
