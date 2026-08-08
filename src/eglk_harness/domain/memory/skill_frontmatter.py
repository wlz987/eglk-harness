"""Parse Agent-Skills-style YAML frontmatter on packaged role templates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

DEFAULT_CORE_SECTIONS: tuple[str, ...] = (
    "Hard rules",
    "Authority boundary",
    "Gate interaction",
    "Relationship to Gate",
    "Gaps vs challenges",
    "Long-run leaves",
    "Long-run / multi-file leaves",
    "Output contract",
    "Output schema",
    "Output JSON",
    "Output JSON shape",
    "Tools",
    "Phase 0 contract",
    "Challenge quality",
    "When to split",
    "Split quality",
    "What to refine",
    "Mechanical contract",
    "Scoring guidance",
    "Quality bar",
)

DEFAULT_EXTENDED_SECTIONS: tuple[str, ...] = (
    "Example",
    "Anti-patterns",
    "Failure modes",
    "Merge / shrink",
)


@dataclass(frozen=True)
class SkillDocument:
    """Parsed role skill template."""

    role: str
    name: str
    description: str
    body: str
    sections: dict[str, str] = field(default_factory=dict)
    core_sections: tuple[str, ...] = DEFAULT_CORE_SECTIONS
    extended_sections: tuple[str, ...] = DEFAULT_EXTENDED_SECTIONS
    allowed_tools: str = ""


def _parse_simple_yaml(raw: str) -> dict[str, Any]:
    """Minimal YAML for frontmatter (no external dependency)."""
    out: dict[str, Any] = {}
    current_list_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        m_list = re.match(r"^\s*-\s+(.*)$", line)
        if m_list and current_list_key:
            out.setdefault(current_list_key, []).append(m_list.group(1).strip().strip('"').strip("'"))
            continue
        m_key = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m_key:
            continue
        key, val = m_key.group(1), m_key.group(2).strip()
        current_list_key = None
        if not val:
            current_list_key = key
            out[key] = []
            continue
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            val = val[1:-1]
        out[key] = val
    return out


def _split_sections(body: str) -> dict[str, str]:
    matches = list(_SECTION_RE.finditer(body))
    if not matches:
        return {"": body.strip()}
    sections: dict[str, str] = {}
    if matches[0].start() > 0:
        preamble = body[:matches[0].start()].strip()
        if preamble:
            sections["Preamble"] = preamble
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[title] = body[start:end].strip()
    return sections


def _section_key(title: str, wanted: str) -> bool:
    a = title.strip().lower()
    b = wanted.strip().lower()
    return a == b or a.startswith(b) or b.startswith(a)


def join_sections(
    sections: dict[str, str],
    wanted_titles: tuple[str, ...],
) -> str:
    """Join skill sections whose headings match ``wanted_titles`` (fuzzy)."""
    parts: list[str] = []
    for want in wanted_titles:
        for title, content in sections.items():
            if _section_key(title, want) and content:
                parts.append(f"## {title}\n\n{content}")
                break
    return "\n\n".join(parts).strip()


def parse_skill_text(role: str, text: str) -> SkillDocument:
    meta: dict[str, Any] = {}
    body = text
    m = _FRONTMATTER_RE.match(text)
    if m:
        meta = _parse_simple_yaml(m.group(1))
        body = text[m.end():]

    name = str(meta.get("name") or role)
    description = str(meta.get("description") or "").strip()
    allowed_tools = str(meta.get("allowed-tools") or meta.get("allowed_tools") or "").strip()

    core_raw = meta.get("core_sections") or meta.get("core-sections")
    ext_raw = meta.get("extended_sections") or meta.get("extended-sections")
    core_sections = tuple(str(x) for x in core_raw) if isinstance(core_raw, list) else DEFAULT_CORE_SECTIONS
    extended_sections = (
        tuple(str(x) for x in ext_raw) if isinstance(ext_raw, list) else DEFAULT_EXTENDED_SECTIONS
    )

    sections = _split_sections(body.strip())
    return SkillDocument(
        role=role,
        name=name,
        description=description,
        body=body.strip(),
        sections=sections,
        core_sections=core_sections,
        extended_sections=extended_sections,
        allowed_tools=allowed_tools,
    )
