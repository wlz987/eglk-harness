"""WorldRef: immutable snapshots and rollback for task workdir files."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass
class WorldRef:
    """Pointer to an immutable pre-tick snapshot directory."""

    snapshot: Path
    revision: int
    meta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": str(self.snapshot),
            "revision": self.revision,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorldRef:
        return cls(
            snapshot=Path(str(data["snapshot"])),
            revision=int(data.get("revision", 0)),
            meta=dict(data.get("meta") or {}),
        )


def _copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    if not src.exists():
        dst.mkdir(parents=True, exist_ok=True)
        return
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns(
            ".eglk-harness",
            ".git",
            ".venv",
            "__pycache__",
            "*.pyc",
            ".pytest_cache",
        ),
        dirs_exist_ok=False,
    )


def snapshot_workdir(
    workdir: Path,
    snapshot_dir: Path,
    *,
    revision: int,
    tick: int,
    meta: Mapping[str, Any] | None = None,
) -> WorldRef:
    """Freeze ``workdir`` into ``snapshot_dir`` (typically ``world/pre_{tick:03d}``)."""
    workdir = workdir.resolve()
    snapshot_dir = snapshot_dir.resolve()
    snapshot_dir.parent.mkdir(parents=True, exist_ok=True)
    _copytree(workdir, snapshot_dir)
    meta_out = {
        "tick": tick,
        "workdir": str(workdir),
        **dict(meta or {}),
    }
    (snapshot_dir / ".worldref.json").write_text(
        json.dumps({"revision": revision, "meta": meta_out}, indent=2) + "\n",
        encoding="utf-8",
    )
    return WorldRef(snapshot=snapshot_dir, revision=revision, meta=meta_out)


def restore(world_ref: WorldRef, workdir: Path) -> WorldRef:
    """Restore workdir from snapshot; returns a new WorldRef with revision+1."""
    workdir = workdir.resolve()
    # Remove tracked content except harness/git — rebuild from snapshot
    if workdir.exists():
        for child in list(workdir.iterdir()):
            if child.name in {".eglk-harness", ".git", ".venv"}:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        workdir.mkdir(parents=True, exist_ok=True)

    for child in world_ref.snapshot.iterdir():
        if child.name == ".worldref.json":
            continue
        dest = workdir / child.name
        if child.is_dir():
            shutil.copytree(child, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(child, dest)

    new_rev = world_ref.revision + 1
    meta = {**world_ref.meta, "restored_from": str(world_ref.snapshot)}
    return WorldRef(snapshot=world_ref.snapshot, revision=new_rev, meta=meta)


def apply_files(workdir: Path, files: Mapping[str, str]) -> list[str]:
    """Apply Claim.payload.files mapping (relative path → content). Returns written paths."""
    workdir = workdir.resolve()
    written: list[str] = []
    for rel, content in files.items():
        rel_s = str(rel).lstrip("/").replace("\\", "/")
        if ".." in Path(rel_s).parts:
            raise ValueError(f"path escape rejected: {rel}")
        if rel_s.startswith(".eglk-harness/") or rel_s in {".goal.md", ".goal_format.md"}:
            # protected paths — skip (orchestrator may log)
            continue
        dest = workdir / rel_s
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        written.append(rel_s)
    return written


def apply_claim_payload(workdir: Path, payload: Mapping[str, Any] | None) -> list[str]:
    """Apply supported Claim payload kinds. Returns list of written relative paths."""
    if not payload:
        return []
    files = payload.get("files")
    if isinstance(files, Mapping):
        return apply_files(workdir, {str(k): str(v) for k, v in files.items()})
    return []
