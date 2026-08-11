"""Oracle path guard — eval overlay may forbid scorer paths on Checker surface (never Gate)."""

from __future__ import annotations

import os


def oracle_forbidden_prefixes() -> list[str]:
    raw = (os.environ.get("EGLK_ORACLE_FORBIDDEN_PREFIXES") or "").strip()
    if not raw:
        return []
    sep = os.pathsep if os.pathsep in raw else ","
    out: list[str] = []
    for part in raw.split(sep):
        s = part.strip()
        if s and s not in out:
            out.append(s)
    return out


def format_oracle_guard_block() -> str:
    prefixes = oracle_forbidden_prefixes()
    if not prefixes:
        return ""
    lines = [
        "[ORACLE_GUARD]",
        "Never read, grep, or cite these paths (benchmark oracle — not for Checker audit):",
    ]
    for p in prefixes:
        lines.append(f"- {p}")
    lines.append("Use scout MCP + on-disk deliverables only.")
    return "\n".join(lines)
