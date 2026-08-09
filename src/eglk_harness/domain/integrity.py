"""Checker integrity monitor — detect workdir mutations during audit."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

_SKIP_NAMES = {
    ".eglk-harness",
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".local",
    ".env",
}


@dataclass
class WorldFingerprint:
    """Content hashes of workdir files (relative paths)."""

    digests: dict[str, str] = field(default_factory=dict)

    def mutated_paths(self, other: WorldFingerprint) -> list[str]:
        changed: list[str] = []
        all_keys = set(self.digests) | set(other.digests)
        for key in sorted(all_keys):
            if self.digests.get(key) != other.digests.get(key):
                changed.append(key)
        return changed


def _should_skip(path: Path, workdir: Path) -> bool:
    try:
        rel = path.relative_to(workdir)
    except ValueError:
        return True
    parts = rel.parts
    if not parts:
        return True
    if parts[0] in _SKIP_NAMES:
        return True
    if any(p == "__pycache__" or p.endswith(".pyc") for p in parts):
        return True
    return False


def fingerprint_workdir(workdir: Path) -> WorldFingerprint:
    """Hash file contents under workdir (excluding harness/git/venv)."""
    workdir = workdir.resolve()
    digests: dict[str, str] = {}
    if not workdir.is_dir():
        return WorldFingerprint(digests)
    for path in sorted(workdir.rglob("*")):
        if not path.is_file():
            continue
        if _should_skip(path, workdir):
            continue
        rel = str(path.relative_to(workdir)).replace("\\", "/")
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        digests[rel] = h
    return WorldFingerprint(digests=digests)


def apply_integrity_flag(
    evidence: dict,
    *,
    before: WorldFingerprint,
    after: WorldFingerprint,
) -> list[str]:
    """If Checker mutated the world, force integrity_violation (never admit)."""
    mutated = before.mutated_paths(after)
    if not mutated:
        return []
    evidence["integrity_violation"] = True
    gaps = list(evidence.get("gaps") or [])
    note = f"checker_wrote_world:{','.join(mutated[:8])}"
    if note not in gaps:
        gaps.append(note)
    evidence["gaps"] = gaps
    return mutated
