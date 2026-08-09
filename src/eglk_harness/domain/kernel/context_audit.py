"""Static audits for GOAL §1.6 (context engineering) and §1.2 (zero HITL)."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

_EMBEDDED_PROMPT_MIN_LEN = 120
_BANNED_EVENT_PREFIXES = ("Ask", "Approve", "HumanGate", "OperatorGate")
_BANNED_CLI_FLAGS = re.compile(r"--(approve|ask|operator|human-gate)\b", re.I)


def scan_event_enum_no_hitl(schema_path: Path) -> tuple[bool, str]:
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    enum = (data.get("properties") or {}).get("type", {}).get("enum") or []
    bad = [t for t in enum if any(str(t).startswith(p) for p in _BANNED_EVENT_PREFIXES)]
    if bad:
        return False, f"hitl_event_types:{bad}"
    status_enum = []
    rp = Path(schema_path.parent / "run_projection.schema.json")
    if rp.is_file():
        rp_data = json.loads(rp.read_text(encoding="utf-8"))
        status_enum = (
            (rp_data.get("properties") or {}).get("run_status", {}).get("enum") or []
        )
    if "waiting_for_human" in status_enum:
        return False, "run_status contains waiting_for_human"
    return True, f"event_types={len(enum)}"


def scan_cli_no_hitl(cli_source: Path) -> tuple[bool, str]:
    text = cli_source.read_text(encoding="utf-8")
    if _BANNED_CLI_FLAGS.search(text):
        return False, "cli contains banned HITL flags"
    return True, "no banned cli flags"


def scan_role_prompts_from_skills(eglk_pkg: Path) -> tuple[bool, str]:
    """Role actors must assemble prompts via skills — not long embedded prose."""
    role_modules = (
        "maker",
        "checker",
        "governor",
        "explorer",
        "verifier",
        "pruner",
        "refiner",
        "compile",
    )
    offenders: list[str] = []
    for role in role_modules:
        path = eglk_pkg / "actors" / role / "__init__.py"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "render_prompt" not in text and "run_bypass_json" not in text:
            offenders.append(f"{role}:no_skill_render")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            s = node.value.strip()
            if len(s) < _EMBEDDED_PROMPT_MIN_LEN or "\n" not in s:
                continue
            if "render_prompt" in s or "topics." in s:
                continue
            offenders.append(f"{role}:{node.lineno}")
    skills_init = eglk_pkg / "domain" / "memory" / "skills" / "__init__.py"
    if not skills_init.is_file():
        return False, "missing memory/skills/__init__.py"
    text = skills_init.read_text(encoding="utf-8")
    if "render_prompt" not in text or "load_skill" not in text:
        return False, "skills module missing render_prompt/load_skill"
    if offenders:
        return False, f"embedded_prompt_literals:{offenders[:5]}"
    return True, "actors use skill templates"


def run_context_audits(eglk_pkg: Path) -> list[dict[str, Any]]:
    schema = eglk_pkg / "domain" / "schemas" / "event.schema.json"
    cli = eglk_pkg / "cli.py"
    checks: list[dict[str, Any]] = []
    ok, detail = scan_event_enum_no_hitl(schema)
    checks.append({"name": "context_audit.events_no_hitl", "ok": ok, "detail": detail})
    if cli.is_file():
        ok, detail = scan_cli_no_hitl(cli)
        checks.append({"name": "context_audit.cli_no_hitl", "ok": ok, "detail": detail})
    ok, detail = scan_role_prompts_from_skills(eglk_pkg)
    checks.append({"name": "context_audit.prompts_from_skills", "ok": ok, "detail": detail})
    return checks
