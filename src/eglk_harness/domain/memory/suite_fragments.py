"""Suite-specific skill fragments (progressive disclosure layer 2)."""

from __future__ import annotations

import os
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Sequence

from eglk_harness.domain.memory.suite_marker import load_marker

_FRAGMENTS_SUBDIR = "fragments"


def _fragment_ids_for_workdir(workdir: Path | None) -> list[str]:
    out: list[str] = []
    env_frags = (os.environ.get("EGLK_SKILL_FRAGMENTS") or "").strip()
    if env_frags:
        sep = os.pathsep if os.pathsep in env_frags else ","
        for part in env_frags.split(sep):
            s = part.strip()
            if s and s not in out:
                out.append(s)

    if workdir is not None:
        marker = load_marker(workdir)
        frags = marker.get("fragments")
        if isinstance(frags, list):
            for f in frags:
                s = str(f).strip()
                if s and s not in out:
                    out.append(s)
    return out


def _fragment_search_roots(workdir: Path | None) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        key = str(path.resolve())
        if key not in seen and path.is_dir():
            seen.add(key)
            roots.append(path.resolve())

    packaged = Path(__file__).resolve().parent / "skills" / _FRAGMENTS_SUBDIR
    if packaged.is_dir():
        _add(packaged)
    legacy = Path(__file__).resolve().parent / _FRAGMENTS_SUBDIR
    if legacy.is_dir():
        _add(legacy)

    raw = (os.environ.get("EGLK_SKILL_FRAGMENTS_DIRS") or os.environ.get("EGLK_SKILL_DIRS") or "").strip()
    if raw:
        sep = os.pathsep if os.pathsep in raw else ","
        for part in raw.split(sep):
            base = Path(part.strip()).expanduser()
            if not str(base).strip():
                continue
            for rel in ("fragments", "skills/fragments"):
                _add(base / rel)

    eval_raw = (os.environ.get("EGLK_EVAL_ROOT") or "").strip()
    suite = (os.environ.get("EGLK_SKILL_SUITE") or "").strip()
    if eval_raw:
        er = Path(eval_raw).expanduser().resolve()
        for rel in ("fragments", "skills/fragments"):
            _add(er / rel)
        if suite:
            _add(er / "skills" / suite / "fragments")

    if workdir is not None:
        wd = Path(workdir).resolve()
        _add(wd / ".eglk-harness" / "skill-overlay" / "fragments")

    return roots


def _load_fragment_text(fragment_id: str, workdir: Path | None = None) -> str | None:
    safe = fragment_id.strip().replace("/", "_")
    if not safe:
        return None
    for root in _fragment_search_roots(workdir):
        here = root / f"{safe}.md"
        if here.is_file():
            return here.read_text(encoding="utf-8").strip()
    try:
        pkg_root = resources.files("eglk_harness.domain.memory.skills") / _FRAGMENTS_SUBDIR
        return (pkg_root / f"{safe}.md").read_text(encoding="utf-8").strip()
    except (FileNotFoundError, TypeError, ModuleNotFoundError, OSError):
        try:
            pkg_root = resources.files("eglk_harness.domain.memory") / _FRAGMENTS_SUBDIR
            return (pkg_root / f"{safe}.md").read_text(encoding="utf-8").strip()
        except (FileNotFoundError, TypeError, ModuleNotFoundError, OSError):
            return None


def render_fragments(
    workdir: Path | None,
    *,
    fragment_ids: Sequence[str] | None = None,
) -> str:
    """Render activated suite fragments for injection into role prompts."""
    ids = list(fragment_ids or _fragment_ids_for_workdir(workdir))
    parts: list[str] = []
    for fid in ids:
        text = _load_fragment_text(fid, workdir)
        if text:
            parts.append(text)
    if not parts:
        return ""
    return "[SUITE_FRAGMENTS]\n\n" + "\n\n---\n\n".join(parts)
