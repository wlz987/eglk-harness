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


_RESTORE_CORE_SKIP = frozenset({".eglk-harness", ".git", ".venv"})
_DEFAULT_PRESERVE_TOP = ("artifacts", "deliverables", "evidence_pack", "agent_runs", "out")


def _preserve_top_dirs(workdir: Path) -> frozenset[str]:
    """Top-level dirs kept across repair restore (delivery / MCP captures).

    Sources (suite-agnostic):
    - always: ``.eglk-harness`` / ``.git`` / ``.venv``
    - env ``EGLK_RESTORE_PRESERVE_DIRS`` (comma-separated top names)
    - first path segment of every ``MUST_EXIST`` constraint in the goal
    """
    import os

    names: set[str] = set(_RESTORE_CORE_SKIP)
    raw = (os.environ.get("EGLK_RESTORE_PRESERVE_DIRS") or ",".join(_DEFAULT_PRESERVE_TOP)).strip()
    for part in raw.split(","):
        top = part.strip().strip("/").split("/")[0]
        if top and top not in {".", ".."}:
            names.add(top)
    try:
        from eglk_harness.domain.kernel.compile_goal import load_goal_constraints
        from eglk_harness.domain.runtime.boundary_verify import parse_boundary_rules

        rules = parse_boundary_rules(load_goal_constraints(workdir))
        for rel, _note in rules.must_exist:
            top = str(rel).strip().strip("/").split("/")[0]
            if top and top not in {".", ".."} and not top.startswith("."):
                names.add(top)
    except Exception:  # noqa: BLE001 — restore must not fail closed on parse
        pass
    return frozenset(names)


def restore(world_ref: WorldRef, workdir: Path) -> WorldRef:
    """Restore workdir from snapshot; returns a new WorldRef with revision+1.

    Delivery top-level dirs (from goal ``MUST_EXIST`` / ``EGLK_RESTORE_PRESERVE_DIRS``)
    are preserved across repair rollback so tool/MCP deliverables are not destroyed
    when Gate retries a leaf.
    """
    workdir = workdir.resolve()
    skip = _preserve_top_dirs(workdir)
    # Remove tracked content except preserve set — rebuild from snapshot
    if workdir.exists():
        for child in list(workdir.iterdir()):
            if child.name in skip:
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
        if child.name in skip and (workdir / child.name).exists():
            continue
        dest = workdir / child.name
        if child.is_dir():
            shutil.copytree(child, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(child, dest)

    new_rev = world_ref.revision + 1
    meta = {**world_ref.meta, "restored_from": str(world_ref.snapshot)}
    return WorldRef(snapshot=world_ref.snapshot, revision=new_rev, meta=meta)


_BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".gz", ".wasm"}


def _looks_like_text_placeholder_for_binary(rel: str, content: str) -> bool:
    """Reject Claim.payload.files that would clobber tool-written binaries with ASCII stubs."""
    suffix = Path(rel).suffix.lower()
    if suffix not in _BINARY_SUFFIXES:
        return False
    # real base64 payloads can be long; placeholders are short ASCII descriptions
    sample = content[:200]
    if "\x00" in content[:64]:
        return False
    if len(content) < 512 and sample.isprintable():
        return True
    return False


def apply_files(workdir: Path, files: Mapping[str, str]) -> list[str]:
    """Apply Claim.payload.files mapping (relative path → content). Returns written paths.

    Refuses ``.goal.md`` / ``.goal_format.md`` / ``.env`` / ``.eglk-harness/**``
    (workdir invariant: runtime models must not rewrite goal or harness config).
    """
    workdir = workdir.resolve()
    protected_hits: list[str] = []
    pending: list[tuple[str, str]] = []
    for rel, content in files.items():
        rel_s = str(rel).lstrip("/").replace("\\", "/")
        if ".." in Path(rel_s).parts:
            raise ValueError(f"path escape rejected: {rel}")
        if rel_s.startswith(".eglk-harness/") or rel_s in {".goal.md", ".goal_format.md", ".env"}:
            protected_hits.append(rel_s)
            continue
        if _looks_like_text_placeholder_for_binary(rel_s, content):
            continue
        pending.append((rel_s, content))
    if protected_hits:
        raise ValueError(
            "protected path refused (invariant: goal/config immutable at runtime): "
            + ", ".join(protected_hits)
        )
    written: list[str] = []
    for rel_s, content in pending:
        dest = workdir / rel_s
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        written.append(rel_s)
    return written


def _ack_or_write(
    workdir: Path,
    rel: str,
    content: Any,
    written: list[str],
) -> None:
    """Write text content when present; otherwise acknowledge an existing file."""
    rel = str(rel).strip().lstrip("/").replace("\\", "/")
    if not rel or ".." in Path(rel).parts:
        return
    if content is not None and not isinstance(content, (Mapping, list, tuple, dict)):
        written.extend(apply_files(workdir, {rel: str(content)}))
        return
    if (workdir / rel).is_file():
        written.append(rel)


def apply_claim_payload(workdir: Path, payload: Mapping[str, Any] | None) -> list[str]:
    """Apply supported Claim payload kinds. Returns list of written or acknowledged paths.

    Accepted ``payload.files`` shapes:
    - ``{rel_path: content_str}`` — write text files
    - ``[{path, content?}, ...]`` — write when content present; else ack existing path
    - ``{key: {path, content?, description?}, ...}`` — nested refs (MCP deliverables);
      never stringify a description-only dict into a root-level stub file
    - nested screenshot lists under a key are path-ack only
    """
    if not payload:
        return []
    files = payload.get("files")
    workdir = workdir.resolve()
    written: list[str] = []
    if isinstance(files, Mapping):
        for key, val in files.items():
            if isinstance(val, str):
                written.extend(apply_files(workdir, {str(key): val}))
                continue
            if isinstance(val, Mapping):
                rel = str(val.get("path") or val.get("file") or key).strip().lstrip("/")
                content = val.get("content")
                if content is None:
                    content = val.get("text")
                # Description-only nested objects must not become stub files at key path
                if content is None and "description" in val and "path" in val:
                    _ack_or_write(workdir, rel, None, written)
                else:
                    _ack_or_write(workdir, rel, content, written)
                continue
            if isinstance(val, list):
                for item in val:
                    if not isinstance(item, Mapping):
                        continue
                    rel = str(item.get("path") or item.get("file") or "").strip().lstrip("/")
                    if not rel:
                        continue
                    content = item.get("content")
                    if content is None:
                        content = item.get("text")
                    _ack_or_write(workdir, rel, content, written)
        return written
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, Mapping):
                continue
            rel = str(item.get("path") or item.get("file") or "").strip().lstrip("/")
            if not rel:
                continue
            content = item.get("content")
            if content is None:
                content = item.get("text")
            _ack_or_write(workdir, rel, content, written)
        return written
    return []
