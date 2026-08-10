"""Episode-layer skill extras (L2): work vs claim passes, format-repair, etc."""

from __future__ import annotations

import os
from functools import lru_cache
from importlib import resources
from pathlib import Path

from eglk_harness.domain.memory.skill_overlay import overlay_search_dirs


def _episode_search_dirs(workdir: Path | None = None) -> list[Path]:
    dirs: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        key = str(path.resolve())
        if key not in seen and path.is_dir():
            seen.add(key)
            dirs.append(path.resolve())

    packaged = Path(__file__).resolve().parent / "episodes"
    if packaged.is_dir():
        _add(packaged)

    raw = (os.environ.get("EGLK_SKILL_DIRS") or "").strip()
    if raw:
        sep = os.pathsep if os.pathsep in raw else ","
        for part in raw.split(sep):
            p = part.strip()
            if p:
                for rel in ("episodes", "episode"):
                    ep = Path(p).expanduser() / rel
                    _add(ep)

    eval_raw = (os.environ.get("EGLK_EVAL_ROOT") or "").strip()
    if eval_raw:
        er = Path(eval_raw).expanduser().resolve()
        for rel in ("episodes", "episode", "skills/episodes", "skills/episode"):
            _add(er / rel)

    if workdir is not None:
        od = Path(workdir).resolve() / ".eglk-harness" / "skill-overlay"
        for rel in ("episodes", "episode"):
            _add(od / rel)

    for base in overlay_search_dirs(workdir):
        for rel in ("episodes", "episode"):
            _add(base / rel)

    return dirs


@lru_cache(maxsize=64)
def _load_episode_raw(name: str) -> str | None:
    safe = name.strip().replace("/", "_")
    if not safe:
        return None
    here = Path(__file__).resolve().parent / "episodes" / f"{safe}.md"
    if here.is_file():
        return here.read_text(encoding="utf-8").strip()
    try:
        root = resources.files("eglk_harness.domain.memory.episodes")
        return (root / f"{safe}.md").read_text(encoding="utf-8").strip()
    except (FileNotFoundError, TypeError, ModuleNotFoundError):
        return None


def load_episode_extra(name: str, workdir: Path | None = None) -> str:
    """Load episode markdown by id (e.g. ``maker_work``, ``maker_claim``)."""
    safe = name.strip().replace("/", "_")
    if not safe:
        return ""
    chunks: list[str] = []
    for base in _episode_search_dirs(workdir):
        p = base / f"{safe}.md"
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text and text not in chunks:
            chunks.append(text)
    if not chunks:
        packaged = _load_episode_raw(safe)
        if packaged:
            chunks.append(packaged)
    return "\n\n".join(chunks)
