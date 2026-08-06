"""Packaged skill templates for Adapter episodes."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path


@lru_cache(maxsize=16)
def load_skill(role: str) -> str:
    """Load ``domain/skills/<role>.md`` text."""
    name = f"{role}.md"
    # Prefer filesystem next to this package (editable installs)
    here = Path(__file__).resolve().parent / name
    if here.is_file():
        return here.read_text(encoding="utf-8")
    try:
        root = resources.files("eglk_harness.domain.skills")
        return (root / name).read_text(encoding="utf-8")
    except (FileNotFoundError, TypeError, ModuleNotFoundError) as exc:
        raise FileNotFoundError(f"skill template missing for role={role!r}") from exc


def render_prompt(role: str, *, leaf_block: str, extra: str = "") -> str:
    skill = load_skill(role)
    parts = [skill.strip(), "", leaf_block.strip()]
    if extra.strip():
        parts.extend(["", extra.strip()])
    parts.append("")
    parts.append("Respond with a single JSON object only (no prose outside JSON).")
    return "\n".join(parts)
