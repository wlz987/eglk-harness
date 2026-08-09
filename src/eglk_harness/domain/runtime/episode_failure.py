"""Classify Adapter episode failures for targeted format-repair hints (suite-agnostic)."""

from __future__ import annotations

import json
import re

_IMAGE_BUDGET_RE = re.compile(
    r"at most\s+(\d+)\s+image",
    re.IGNORECASE,
)


def failure_kind_from_raw(raw: str) -> str | None:
    """Return a short failure kind from Codex/Claude NDJSON or stderr text."""
    text = str(raw or "")
    if not text.strip():
        return None
    # Codex turn.failed envelope
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "turn.failed":
            err = obj.get("error")
            if isinstance(err, dict):
                msg = str(err.get("message") or "")
            else:
                msg = str(err or "")
            if _IMAGE_BUDGET_RE.search(msg):
                return "image_budget"
            if msg.strip():
                return "turn_failed"
    if _IMAGE_BUDGET_RE.search(text):
        return "image_budget"
    if "codex_timeout" in text or "timeout" in text.lower():
        return "timeout"
    return None


def failure_repair_extra(kind: str | None) -> str:
    """Extra format-repair instructions — never re-opens tools."""
    if kind == "image_budget":
        return (
            "TURN FAILED: inference image budget exceeded. "
            "Do NOT request more screenshots or vision in repair. "
            "Emit Claim JSON only from work already on disk (paths, meta.json, snapshots). "
            "If boundary lists MUST_EXIST deliverables you cannot verify from text, set "
            "`done_progress` ≤ 0.45 and note missing files in `step_review.losses` — "
            "do not claim 1.0 without those paths."
        )
    if kind == "turn_failed":
        return (
            "Previous Maker turn failed before a valid Claim. "
            "Emit Claim JSON from existing workdir artifacts only — no tools in repair."
        )
    if kind == "timeout":
        return (
            "Previous episode timed out. Emit best-effort Claim JSON from known artifacts; "
            "do not claim full completion without boundary files on disk."
        )
    return ""
