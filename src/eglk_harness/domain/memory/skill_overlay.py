"""Optional role skill overlays from eval / operator paths (suite-agnostic loader)."""

from __future__ import annotations

import os
from pathlib import Path


def overlay_search_dirs(workdir: Path | None = None) -> list[Path]:
    """Directories scanned for ``<role>.md`` overlays (first match per dir wins)."""
    dirs: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        key = str(path.resolve())
        if key not in seen and path.is_dir():
            seen.add(key)
            dirs.append(path.resolve())

    raw = (os.environ.get("EGLK_SKILL_DIRS") or "").strip()
    if raw:
        sep = os.pathsep if os.pathsep in raw else ","
        for part in raw.split(sep):
            p = part.strip()
            if p:
                _add(Path(p).expanduser())

    eval_raw = (os.environ.get("EGLK_EVAL_ROOT") or "").strip()
    if eval_raw:
        er = Path(eval_raw).expanduser().resolve()
        skills = er / "skills"
        if skills.is_dir():
            _add(skills)

    if workdir is not None:
        od = Path(workdir).resolve() / ".eglk-harness" / "skill-overlay"
        if od.is_dir():
            _add(od)

    return dirs


def load_role_overlay(role: str, workdir: Path | None = None) -> str:
    """Concatenate overlay markdown for ``role`` from injected skill dirs."""
    role = str(role).strip().lower()
    if not role:
        return ""
    chunks: list[str] = []
    for base in overlay_search_dirs(workdir):
        for rel in (f"{role}.md", f"skills/{role}.md"):
            p = base / rel
            if not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if text and text not in chunks:
                chunks.append(text)
    return "\n\n".join(chunks)
