"""Parse human ``.goal.md`` text for run metadata."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from eglk_harness.domain.kernel import paths

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

def done_criteria(text: str, *, default: str = "hello.txt exists") -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^[-*]\s*\[[ xX]?\]\s*(.+)$", line.strip())
        if m:
            items.append(m.group(1).strip())
    return items or [default]
