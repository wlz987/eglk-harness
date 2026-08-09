"""Advisor / scout must not write main-chain authority dirs."""

from __future__ import annotations

from pathlib import Path

# Relative path prefixes under workdir or loop_dir that advisors must not write.
MAIN_RING_WRITE_FORBIDDEN = frozenset(
    {
        "claims",
        "evidence",
        "decisions",
    }
)


def is_main_ring_authority_path(path: Path, *, loop_dir: Path | None = None) -> bool:
    """True if ``path`` is under claims/evidence/decisions (loop authority projections)."""
    path = path.resolve()
    parts = set(path.parts)
    if parts & MAIN_RING_WRITE_FORBIDDEN:
        # Prefer loop_dir-scoped check when provided
        if loop_dir is not None:
            try:
                rel = path.relative_to(loop_dir.resolve())
            except ValueError:
                return False
            return bool(rel.parts) and rel.parts[0] in MAIN_RING_WRITE_FORBIDDEN
        return True
    return False


def assert_advisor_path_allowed(path: Path, *, loop_dir: Path) -> None:
    """Raise ``PermissionError`` if advisor attempts to write main-ring dirs."""
    if is_main_ring_authority_path(path, loop_dir=loop_dir):
        raise PermissionError(
            f"advisor/swarm must not write main-ring path: {path} "
            f"(allowed: candidates/, scout/, sigma/refined/)"
        )


def advisor_write_guard(loop_dir: Path, path: Path) -> Path:
    """Return path after validating it is not a main-ring authority write."""
    assert_advisor_path_allowed(path, loop_dir=loop_dir)
    return path
