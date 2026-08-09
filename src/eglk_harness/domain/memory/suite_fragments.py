"""Suite-specific skill fragments (progressive disclosure layer 2)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Sequence

from eglk_harness.domain.memory.suite_marker import load_marker

_FRAGMENTS_SUBDIR = "fragments"


def _fragment_ids_for_workdir(workdir: Path | None) -> list[str]:
    ids: list[str] = []
    env_suite = (os.environ.get("EGLK_SKILL_SUITE") or "").strip()
    if env_suite:
        ids.append(env_suite)

    if workdir is not None:
        marker = load_marker(workdir)
        suite = str(marker.get("suite") or "").strip()
        if suite and suite not in ids:
            ids.append(suite)
        frags = marker.get("fragments")
        if isinstance(frags, list):
            for f in frags:
                s = str(f).strip()
                if s and s not in ids:
                    ids.append(s)

        mcp_dir = workdir / ".eglk-harness" / "mcp"
        if (mcp_dir / "wa-browser.mcp.json").is_file() and "wa-browser" not in ids:
            ids.append("wa-browser")

        for name in ("wa-browser.mcp.json", "mcp.json"):
            cfg_path = mcp_dir / name
            if not cfg_path.is_file():
                continue
            try:
                raw = json.loads(cfg_path.read_text(encoding="utf-8"))
                servers = raw.get("mcpServers") if isinstance(raw, dict) else None
                if isinstance(servers, dict):
                    for srv in servers:
                        if "wa-browser" in str(srv).lower() and "wa-browser" not in ids:
                            ids.append("wa-browser")
                        if "computer" in str(srv).lower() and "computer-use" not in ids:
                            ids.append("computer-use")
            except (OSError, json.JSONDecodeError):
                continue

    suite_to_frag: dict[str, str] = {
        "wa_hard": "wa-browser",
        "weave_lh": "computer-use",
        "osworld_aux": "computer-use",
        "tb21": "terminal-bench",
    }
    out: list[str] = []
    for item in ids:
        mapped = suite_to_frag.get(item, item)
        if mapped not in out:
            out.append(mapped)
    return out


@lru_cache(maxsize=32)
def _load_fragment_text(fragment_id: str) -> str | None:
    safe = fragment_id.strip().replace("/", "_")
    if not safe:
        return None
    here = Path(__file__).resolve().parent / _FRAGMENTS_SUBDIR / f"{safe}.md"
    if here.is_file():
        return here.read_text(encoding="utf-8").strip()
    try:
        root = resources.files("eglk_harness.domain.memory") / _FRAGMENTS_SUBDIR
        return (root / f"{safe}.md").read_text(encoding="utf-8").strip()
    except (FileNotFoundError, TypeError, ModuleNotFoundError):
        return None


def render_fragments(
    workdir: Path | None,
    *,
    fragment_ids: Sequence[str] | None = None,
) -> str:
    """Render activated suite fragments for injection into leaf_block."""
    ids = list(fragment_ids or _fragment_ids_for_workdir(workdir))
    parts: list[str] = []
    for fid in ids:
        if fid in {"wa_hard", "weave_lh", "osworld_aux", "tb21"}:
            continue
        text = _load_fragment_text(fid)
        if text:
            parts.append(text)
    if not parts:
        return ""
    return "[SUITE_FRAGMENTS]\n\n" + "\n\n---\n\n".join(parts)


def format_tool_profile_line(role: str) -> str:
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
