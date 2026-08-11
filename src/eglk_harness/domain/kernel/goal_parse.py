"""Parse human ``.goal.md`` text for run metadata and intent criteria."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from eglk_harness.domain.kernel import paths

INTENT_CRITERIA_FALLBACK = "Satisfy the goal intent stated in Summary with inspectable deliverables"
_INTENT_FALLBACK = INTENT_CRITERIA_FALLBACK
_SUMMARY_HEADERS = frozenset({"summary"})
_ACCEPTANCE_HEADERS = frozenset(
    {
        "acceptance",
        "done",
        "done criteria",
        "success criteria",
        "checklist",
        "验收",
        "完成条件",
    }
)
_CHECKBOX_RE = re.compile(r"^[-*]\s*\[[ xX]?\]\s*(.+)$")
_BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$")
_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$")


def read_goal_text(workdir: Path, goal: str | None = None) -> str:
    if goal:
        p = Path(goal)
        if p.is_file():
            return p.read_text(encoding="utf-8")
        return goal
    return paths.goal_path(workdir).read_text(encoding="utf-8")


def goal_id(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"g-{digest}"


def title_from_goal(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip() or "goal"
    return "goal"


def section_bullets(goal_text: str, *headers: str) -> list[str]:
    """Collect bullet lines under markdown sections whose titles match ``headers``."""
    want = {h.lower() for h in headers}
    lines = goal_text.splitlines()
    out: list[str] = []
    capture = False
    for line in lines:
        h = _HEADING_RE.match(line.strip())
        if h:
            capture = h.group(1).strip().lower() in want
            continue
        if not capture:
            continue
        m = _BULLET_RE.match(line)
        if m:
            out.append(m.group(1).strip())
    return out


def summary_intent_lines(goal_text: str) -> list[str]:
    """Non-bullet intent lines under ``## Summary`` (first block until blank or next heading)."""
    lines = goal_text.splitlines()
    capture = False
    out: list[str] = []
    for line in lines:
        h = _HEADING_RE.match(line.strip())
        if h:
            title = h.group(1).strip().lower()
            capture = title in _SUMMARY_HEADERS
            if capture:
                out = []
            continue
        if not capture:
            continue
        if not line.strip():
            if out:
                break
            continue
        if _BULLET_RE.match(line):
            continue
        out.append(line.strip())
    return out


def checkbox_criteria(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        m = _CHECKBOX_RE.match(line.strip())
        if m:
            items.append(m.group(1).strip())
    return items


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def intent_criteria(text: str) -> list[str]:
    """Extract root acceptance criteria from goal text (intent-first; no hello.txt default).

    Priority (merge, dedupe, preserve order):
      1. Markdown checkboxes
      2. ## Summary intent lines (joined as one statement if multiple short lines)
      3. Acceptance / Done / Success criteria section bullets
      4. Macro fallback (never ``hello.txt exists`` without explicit mention)
    """
    items: list[str] = []
    items.extend(checkbox_criteria(text))

    summary_lines = summary_intent_lines(text)
    if summary_lines:
        joined = " ".join(summary_lines).strip()
        if joined:
            items.append(joined)

    items.extend(section_bullets(text, *sorted(_ACCEPTANCE_HEADERS)))

    if not items:
        loose = loose_bullets(text)
        if loose:
            items.extend(loose[:8])

    items = _dedupe_preserve(items)
    if items:
        return items
    return [_INTENT_FALLBACK]


def done_criteria(text: str, *, default: str | None = None) -> list[str]:
    """Legacy alias for ``intent_criteria`` — do not use for new call sites."""
    if default is not None:
        items = checkbox_criteria(text)
        return items or [default]
    return intent_criteria(text)


def loose_bullets(goal_text: str) -> list[str]:
    return [
        m.group(1).strip()
        for line in goal_text.splitlines()
        if (m := _BULLET_RE.match(line))
    ]
