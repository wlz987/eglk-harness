"""Packaged skill templates for Adapter episodes."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from importlib import resources
from pathlib import Path

from eglk_harness.domain.memory.skill_frontmatter import join_sections, parse_skill_text, SkillDocument
from eglk_harness.domain.memory.skill_overlay import load_role_overlay


class DisclosureLevel(str, Enum):
    """How much of a role skill template to inject (Agent Skills progressive disclosure)."""

    METADATA = "metadata"
    CORE = "core"
    FULL = "full"


_JSON_ROLES: frozenset[str] = frozenset(
    {
        "maker",
        "checker",
        "explorer",
        "verifier",
        "pruner",
        "governor",
        "refiner",
        "compile",
    }
)


def format_tool_profile_line(role: str) -> str:
    """Mirror ``tool_policy`` for skill header (not suite-specific)."""
    from eglk_harness.domain.adapters.tool_policy import resolve_role_tool_profile

    profile = resolve_role_tool_profile(role)
    if not profile.tools_allowed:
        return "tools-off (role profile or EGLK_TOOLS_OFF_ROLES)"
    if profile.mcp_server_allowlist is None:
        return "tools-on; MCP unrestricted (EGLK_MCP_ALLOW_<ROLE> unset)"
    if not profile.mcp_server_allowlist:
        return "tools-on; MCP servers none (allowlist empty)"
    servers = ", ".join(sorted(profile.mcp_server_allowlist))
    return f"tools-on; MCP allowlist: {servers}"


@lru_cache(maxsize=32)
def _load_skill_raw(role: str) -> str:
    name = f"{role}.md"
    here = Path(__file__).resolve().parent / name
    if here.is_file():
        return here.read_text(encoding="utf-8")
    try:
        root = resources.files("eglk_harness.domain.memory.skills")
        return (root / name).read_text(encoding="utf-8")
    except (FileNotFoundError, TypeError, ModuleNotFoundError) as exc:
        raise FileNotFoundError(f"skill template missing for role={role!r}") from exc


@lru_cache(maxsize=32)
def load_skill_document(role: str) -> SkillDocument:
    return parse_skill_text(role, _load_skill_raw(role))


def load_skill(role: str) -> str:
    """Load full skill body (frontmatter stripped)."""
    return load_skill_document(role).body


def load_skill_metadata(role: str) -> dict[str, str]:
    """Agent Skills index entry: name + description + tool profile."""
    doc = load_skill_document(role)
    return {
        "name": doc.name,
        "description": doc.description,
        "allowed_tools": doc.allowed_tools or format_tool_profile_line(role),
    }


def _render_skill_body(doc: SkillDocument, disclosure: DisclosureLevel, format_repair: bool) -> str:
    if format_repair or disclosure == DisclosureLevel.FULL:
        return doc.body
    if disclosure == DisclosureLevel.METADATA:
        return ""
    return join_sections(doc.sections, doc.core_sections)


def render_prompt(
    role: str,
    *,
    leaf_block: str,
    extra: str = "",
    workdir: Path | None = None,
    disclosure: DisclosureLevel = DisclosureLevel.CORE,
    format_repair: bool = False,
) -> str:
    """Assemble role skill + leaf contract block for one Adapter episode.

    ``workdir`` is accepted for API stability; boundaries come from ``leaf_block``
    (assembled from human goal / leaf contract), not benchmark-specific harness hooks.
    """
    _ = workdir
    doc = load_skill_document(role)
    tool_line = doc.allowed_tools or format_tool_profile_line(role)
    header = (
        f"[SKILL {doc.name}]\n"
        f"{doc.description}\n"
        f"allowed-tools: {tool_line}"
    )
    skill_body = _render_skill_body(doc, disclosure, format_repair)
    parts: list[str] = [header]
    if skill_body:
        parts.extend(["", skill_body.strip()])
    overlay = load_role_overlay(role, workdir)
    if overlay.strip():
        parts.extend(["", "[INJECTED SKILL]", overlay.strip()])
    block = leaf_block.strip()
    if block:
        parts.extend(["", block])
    if extra.strip():
        parts.extend(["", extra.strip()])
    if role in _JSON_ROLES:
        parts.append("")
        parts.append("Respond with a single JSON object only (no prose outside JSON).")
        if role == "maker":
            parts.append(
                "Required: step_review with gains/losses/benefits/risks "
                "(本步得失、收益、风险；each a non-empty string array)."
            )
    return "\n".join(parts)
