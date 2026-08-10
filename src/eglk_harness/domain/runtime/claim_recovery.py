"""Recover ActionClaim from episode artifacts without another LLM call."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eglk_harness.domain.kernel.schema_validate import try_parse_document


def _visible_path_for_tee(tee_path: str | Path) -> Path | None:
    p = Path(tee_path)
    if p.name.endswith(".jsonl"):
        return Path(str(p.with_name(p.name[:-len(".jsonl")])) + ".visible.txt")
    if p.suffix:
        return p.with_suffix(".visible.txt")
    return Path(str(p) + ".visible.txt")


def recover_claim_from_episode(
    tee_path: str | Path | None,
    text: str | None = None,
) -> dict[str, Any] | None:
    """Parse claim JSON from tee sidecar or raw episode text (format-repair fast path)."""
    sources: list[str] = []
    if text and str(text).strip():
        sources.append(str(text))
    if tee_path:
        vis = _visible_path_for_tee(tee_path)
        if vis is not None and vis.is_file():
            sources.append(vis.read_text(encoding="utf-8"))
        raw_path = Path(tee_path)
        if raw_path.is_file() and raw_path.suffix == ".jsonl":
            for line in raw_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("2026-") and "ERROR" in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                item = rec.get("item") if isinstance(rec, dict) else None
                if isinstance(item, dict) and item.get("type") == "agent_message":
                    msg = item.get("text")
                    if isinstance(msg, str) and msg.strip():
                        sources.append(msg)
    seen: set[str] = set()
    for src in sources:
        key = src[:200]
        if key in seen:
            continue
        seen.add(key)
        parsed, errs = try_parse_document("claim", src)
        if parsed is not None and not errs:
            return parsed
    return None
