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

# Tiny literal stub files (not multi-MB captures with incidental HTML attributes).
_STUB_MAX_BYTES = 4096
_STUB_TEXT_RE = re.compile(
    r"^\s*(\[binary[^\]]*\]|placeholder\s*har|todo:\s*har|stub\s*har)\s*$",
    re.IGNORECASE,
)


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


def _is_text_stub_capture(path: Path) -> bool:
    """True for small hand-written stub files, not real browser captures."""
    try:
        size = path.stat().st_size
    except OSError:
        return True
    if size == 0:
        return True
    if size > _STUB_MAX_BYTES:
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return True
    if not text:
        return True
    if text.lower().startswith("[binary"):
        return True
    return bool(_STUB_TEXT_RE.match(text))


def _har_json_valid(path: Path) -> bool:
    """Parse HAR JSON structure; ignore incidental ``placeholder=`` in captured HTML."""
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict) or "log" not in data:
        return False
    log = data.get("log")
    if not isinstance(log, dict):
        return False
    entries = log.get("entries")
    if not isinstance(entries, list) or len(entries) < 1:
        return False
    return True


def _is_placeholder_capture(path: Path) -> bool:
    """True when a HAR-style network capture is missing, stub, or incomplete JSON."""
    if not path.is_file():
        return True
    if _is_text_stub_capture(path):
        return True
    return not _har_json_valid(path)


_DELIVERABLE_HINT_REL = (
    ".eglk-harness/deliverable_hint.json",
    ".deliverable_hint.json",
)


def _load_deliverable_hint(path: Path) -> dict | None:
    """Walk up from deliverable toward workdir roots for optional hint sidecar."""
    cur = path.parent
    for _ in range(8):
        for rel in _DELIVERABLE_HINT_REL:
            cand = cur / rel
            if not cand.is_file():
                continue
            try:
                raw = json.loads(cand.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeError):
                continue
            if isinstance(raw, dict):
                return raw
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _matches_hint_placeholder(data: dict, hint: dict) -> bool:
    """True when ``data`` equals hint ``example_success`` on configured keys."""
    example = hint.get("example_success")
    if not isinstance(example, dict):
        return False
    when = hint.get("placeholder_when")
    if isinstance(when, dict):
        for key, expected in when.items():
            actual = data.get(key)
            if str(actual or "").upper() != str(expected).upper():
                return False
    keys = hint.get("placeholder_keys")
    if keys is None:
        keys = [k for k in example if not str(k).startswith("_")]
    if not isinstance(keys, list) or not keys:
        return False
    for key in keys:
        key_s = str(key)
        if key_s in example and data.get(key_s) != example.get(key_s):
            return False
    return True


def _is_placeholder_structured_json(path: Path) -> bool:
    """True when JSON deliverable is invalid or a schema-template copy from hint."""
    if not path.is_file() or path.stat().st_size == 0:
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return True
    if not isinstance(data, dict):
        return True
    if data.get("_placeholder") is True:
        return True
    hint = _load_deliverable_hint(path)
    if hint is None:
        return False
    return _matches_hint_placeholder(data, hint)


def is_valid_must_exist_file(path: Path, *, rel: str) -> bool:
    """Whether ``path`` satisfies a MUST_EXIST entry for ``rel``."""
    if not path.is_file():
        return False
    if rel.endswith(".har"):
        return not _is_placeholder_capture(path)
    if Path(rel).suffix.lower() == ".json" and _load_deliverable_hint(path) is not None:
        return not _is_placeholder_structured_json(path)
    return path.stat().st_size > 0


def _partial_path(final: Path) -> Path:
    return final.with_name(final.name + ".partial")


def promote_staged_deliverables(workdir: Path, boundary: Sequence[str]) -> list[str]:
    """Atomically promote ``<must_exist>.partial`` → final when partial is valid.

    Suite-agnostic staging convention: tools write ``path.partial``, finalize/heal
    promotes only when the partial passes the same validity checks as the final.
    Never replaces an already-valid final with a worse partial.
    """
    workdir = workdir.resolve()
    promoted: list[str] = []
    rules = parse_boundary_rules(boundary)
    for rel, _note in rules.must_exist:
        final = workdir / rel
        partial = _partial_path(final)
        if not partial.is_file():
            continue
        if not is_valid_must_exist_file(partial, rel=rel):
            continue
        if is_valid_must_exist_file(final, rel=rel):
            # Keep good final; drop stale partial.
            try:
                partial.unlink()
            except OSError:
                pass
            continue
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            try:
                final.unlink()
            except OSError:
                continue
        try:
            partial.replace(final)
            promoted.append(rel)
        except OSError:
            continue
    return promoted


def _forbidden_hits(workdir: Path, prefixes: Sequence[str]) -> list[str]:
    """Flag existing paths that match a forbidden prefix (generic, not suite-specific)."""
    hits: list[str] = []
    for prefix in prefixes:
        p = prefix.strip().rstrip("/")
        if not p:
            continue
        base = workdir / p
        if base.exists():
            hits.append(f"forbidden path exists: {p}")
            continue
        parent_rel = str(Path(p).parent).replace("\\", "/")
        name_pref = Path(p).name
        parent = workdir if parent_rel in {".", ""} else workdir / parent_rel
        if not parent.is_dir():
            continue
        for child in parent.iterdir():
            rel = (
                child.name
                if parent_rel in {".", ""}
                else f"{parent_rel}/{child.name}".replace("\\", "/")
            )
            if rel.startswith(p) or (name_pref and child.name.startswith(name_pref)):
                hits.append(f"forbidden path exists: {rel}")
    return hits


def verify_boundary(workdir: Path, boundary: Sequence[str]) -> list[str]:
    """Return blocking gap messages for mechanical boundary violations."""
    workdir = workdir.resolve()
    promote_staged_deliverables(workdir, boundary)
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
        if rel.endswith(".har") and _is_placeholder_capture(path):
            violations.append(f"boundary: {rel} is not a valid HAR (placeholder or missing log)")
            continue
        if Path(rel).suffix.lower() == ".json" and _load_deliverable_hint(path) is not None and _is_placeholder_structured_json(
            path
        ):
            msg = f"boundary: {rel} looks like a schema placeholder, not an observation-bound deliverable"
            if note:
                msg += f" ({note})"
            violations.append(msg)

    for hit in _forbidden_hits(workdir, rules.forbidden_prefixes):
        violations.append(f"boundary: {hit}")

    return violations


def apply_boundary_to_evidence(
    evidence: dict,
    *,
    workdir: Path,
    boundary: Sequence[str],
) -> dict:
    """Merge mechanical boundary violations into Evidence ``additional_gaps`` / verdict gaps."""
    violations = verify_boundary(workdir, boundary)
    if not violations:
        return evidence
    out = dict(evidence)
    extra = [str(g) for g in (out.get("additional_gaps") or [])]
    for v in violations:
        if v not in extra:
            extra.append(v)
    out["additional_gaps"] = extra
    verdicts = out.get("verdicts")
    if isinstance(verdicts, list):
        patched: list[dict] = []
        for verdict in verdicts:
            if not isinstance(verdict, dict):
                continue
            vd = dict(verdict)
            if vd.get("status") == "satisfied":
                vd["status"] = "unsatisfied"
            vgaps = [str(g) for g in (vd.get("gaps") or [])]
            for v in violations:
                if v not in vgaps:
                    vgaps.append(v)
            vd["gaps"] = vgaps
            patched.append(vd)
        out["verdicts"] = patched
    return out
