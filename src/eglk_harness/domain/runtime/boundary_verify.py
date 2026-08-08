"""Mechanical boundary checks from leaf_contract boundary directives."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


@dataclass
class BoundaryRules:
    must_exist: list[tuple[str, str]] = field(default_factory=list)  # (rel_path, note)
    forbidden_prefixes: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)


_MUST_EXIST_RE = re.compile(
    r"^MUST_EXIST:\s*([^\s(]+)(?:\s*\(([^)]*)\))?\s*$",
    re.IGNORECASE,
)
_FORBIDDEN_RE = re.compile(r"^FORBIDDEN_PATH_PREFIX:\s*(.+)$", re.IGNORECASE)
_USE_MCP_RE = re.compile(r"^USE_MCP:\s*(.+)$", re.IGNORECASE)
_FORBIDDEN_TEXT_RE = re.compile(r"^FORBIDDEN:\s*(.+)$", re.IGNORECASE)


def parse_boundary_rules(boundary: Sequence[str]) -> BoundaryRules:
    rules = BoundaryRules()
    for raw in boundary:
        line = str(raw).strip()
        if not line:
            continue
        m = _MUST_EXIST_RE.match(line)
        if m:
            rules.must_exist.append((m.group(1).strip(), (m.group(2) or "").strip()))
            continue
        m = _FORBIDDEN_RE.match(line)
        if m:
            rules.forbidden_prefixes.append(m.group(1).strip())
            continue
        m = _USE_MCP_RE.match(line)
        if m:
            rules.hints.append(f"USE_MCP: {m.group(1).strip()}")
            continue
        m = _FORBIDDEN_TEXT_RE.match(line)
        if m:
            rules.hints.append(f"FORBIDDEN: {m.group(1).strip()}")
            continue
        if line.startswith("Σ:"):
            continue
        if line.startswith("skill "):
            continue
    return rules


def _is_placeholder_har(path: Path) -> bool:
    if not path.is_file():
        return True
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.lower().startswith("[binary") or "placeholder" in stripped.lower():
        return True
    try:
        data = json.loads(text)
        return not isinstance(data, dict) or "log" not in data
    except json.JSONDecodeError:
        return path.stat().st_size < 64


def _forbidden_hits(workdir: Path, prefixes: Sequence[str]) -> list[str]:
    hits: list[str] = []
    for prefix in prefixes:
        p = prefix.strip()
        if not p:
            continue
        base = workdir / p
        if base.exists():
            hits.append(f"forbidden path exists: {p}")
        # Also scan agent_runs for matching prefixes
        agent_runs = workdir / "agent_runs"
        if agent_runs.is_dir():
            for child in agent_runs.iterdir():
                rel = f"agent_runs/{child.name}"
                if rel.startswith(p) or child.name.startswith(p.replace("agent_runs/", "")):
                    hits.append(f"forbidden path exists: {rel}")
    return hits


def verify_boundary(workdir: Path, boundary: Sequence[str]) -> list[str]:
    """Return blocking gap messages for mechanical boundary violations."""
    rules = parse_boundary_rules(boundary)
    violations: list[str] = []

    for rel, note in rules.must_exist:
        path = workdir / rel
        if not path.is_file():
            msg = f"boundary: missing required file {rel}"
            if note:
                msg += f" ({note})"
            violations.append(msg)
            continue
        if rel.endswith(".har") and _is_placeholder_har(path):
            violations.append(f"boundary: {rel} is not a valid HAR (placeholder or missing log)")

    for hit in _forbidden_hits(workdir, rules.forbidden_prefixes):
        violations.append(f"boundary: {hit}")

    return violations


def apply_boundary_to_evidence(
    evidence: dict,
    *,
    workdir: Path,
    boundary: Sequence[str],
) -> dict:
    """Merge mechanical boundary violations into Checker Evidence gaps."""
    violations = verify_boundary(workdir, boundary)
    if not violations:
        return evidence
    out = dict(evidence)
    gaps = list(out.get("gaps") or [])
    for v in violations:
        if v not in gaps:
            gaps.append(v)
    out["gaps"] = gaps
    artifacts = list(out.get("artifacts") or [])
    for v in violations:
        tag = f"[boundary] {v}"
        if tag not in artifacts:
            artifacts.append(tag)
    out["artifacts"] = artifacts
    try:
        audit = float(out.get("audit_progress", 1.0))
    except (TypeError, ValueError):
        audit = 1.0
    out["audit_progress"] = min(audit, 0.45)
    return out
