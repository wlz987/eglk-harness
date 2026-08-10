"""Per-workdir suite marker for skill fragments and mechanical boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel import paths

SUITE_MARKER_NAME = "suite.json"


def marker_path(workdir: Path) -> Path:
    return paths.harness_root(workdir) / SUITE_MARKER_NAME


def load_marker(workdir: Path) -> dict[str, Any]:
    p = marker_path(workdir)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def write_marker(
    workdir: Path,
    *,
    suite: str,
    task_id: str | None = None,
    fragments: Sequence[str] | None = None,
    boundary: Sequence[str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Path:
    """Write ``.eglk-harness/suite.json`` for fragment routing and boundary checks."""
    paths.harness_root(workdir).mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {
        "suite": suite,
        "task_id": task_id,
        "fragments": [str(x) for x in (fragments or ())],
        "boundary": [str(x) for x in (boundary or [])],
    }
    if extra:
        doc.update(dict(extra))
    p = marker_path(workdir)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def boundary_lines(workdir: Path) -> list[str]:
    marker = load_marker(workdir)
    raw = marker.get("boundary")
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if str(x).strip()]
