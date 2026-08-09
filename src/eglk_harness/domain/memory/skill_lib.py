"""Skill library K under ``.eglk-harness/memory/skills/``."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel import paths
from eglk_harness.domain.memory.lifecycle import load_active_records
from eglk_harness.domain.memory.sigma import save_active_record

def skills_root(workdir: Path) -> Path:
    d = paths.memory_skills_dir(workdir)
    d.mkdir(parents=True, exist_ok=True)
    return d

def _index_path(workdir: Path) -> Path:
    return skills_root(workdir) / "index.json"

def load_index(workdir: Path) -> list[dict[str, Any]]:
    p = _index_path(workdir)
    if not p.is_file():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []

def save_index(workdir: Path, items: list[dict[str, Any]]) -> None:
    _index_path(workdir).write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

def _skill_dir(workdir: Path, skill_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", skill_id)[:80]
    d = skills_root(workdir) / safe
    d.mkdir(parents=True, exist_ok=True)
    return d

def _write_skill_files(workdir: Path, entry: Mapping[str, Any], body: str) -> Path:
    d = _skill_dir(workdir, str(entry.get("id") or "skill"))
    (d / "meta.json").write_text(
        json.dumps(dict(entry), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (d / "SKILL.md").write_text(body.strip() + "\n", encoding="utf-8")
    return d

def record_admit(
    workdir: Path,
    *,
    leaf_id: str,
    title: str,
    tick: int,
    claim: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bump or create a skill entry after Gate admit (K bump_for_leaf)."""
    items = load_index(workdir)
    key = f"leaf:{leaf_id}"
    found: dict[str, Any] | None = None
    for it in items:
        if it.get("id") == key:
            found = it
            break
    if found is None:
        found = {
            "id": key,
            "name": title or leaf_id,
            "version": 1,
            "usage_count": 0,
            "status": "active",
            "triggers": [leaf_id],
            "derived_from": [],
            "history": [],
        }
        items.append(found)
    found["usage_count"] = int(found.get("usage_count") or 0) + 1
    found["version"] = int(found.get("version") or 1)
    hist = list(found.get("history") or [])
    note = ""
    if isinstance(claim, Mapping):
        sr = claim.get("step_review")
        if isinstance(sr, dict):
            bens = sr.get("benefits") or []
            if isinstance(bens, list) and bens:
                note = str(bens[0])[:200]
    hist.append({"tick": tick, "event": "admit", "note": note})
    found["history"] = hist[-20:]
    save_index(workdir, items)
    body = (
        f"---\n"
        f"name: {found.get('id')}\n"
        f"description: {str(found.get('name') or found.get('id'))[:200]}\n"
        f"---\n\n"
        f"# {found.get('name')}\n\n"
        f"Leaf skill reinforced on admit (tick={tick}).\n\n"
        f"- triggers: {', '.join(str(t) for t in found.get('triggers') or [])}\n"
        f"- usage_count: {found.get('usage_count')}\n"
        f"- last_note: {note or '(none)'}\n"
    )
    _write_skill_files(workdir, found, body)
    return found

# Design alias (K · bump_for_leaf)
bump_for_leaf = record_admit

def distill_from_sigma(
    workdir: Path,
    *,
    min_conf: float = 0.8,
    min_verifications: int = 2,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Promote high-confidence Σ hits/lessons into K skills (sigma→K promotion contract)."""
    active = load_active_records(workdir)
    items = load_index(workdir)
    by_id = {str(it.get("id")): it for it in items}
    created: list[dict[str, Any]] = []
    for σ in active:
        if not isinstance(σ, Mapping):
            continue
        conf = float(σ.get("conf") or 0)
        kind = str(σ.get("kind") or "")
        verifications = int(σ.get("verifications") or σ.get("hits") or 0)
        if conf < min_conf or kind not in {"hit", "lesson"}:
            continue
        if verifications < min_verifications and kind != "hit":
            # hits from admit may start with verifications=0 — require conf>=0.85 alone
            if conf < 0.85:
                continue
        sid = str(σ.get("id") or "")
        if not sid:
            continue
        # leaf-id shaped cond → skip (one-shot)
        cond = str(σ.get("cond") or "")
        if re.search(r"\bsg_\d", cond) or re.search(r"\bsg_\d", sid):
            continue
        key = f"sigma:{sid}"
        if key in by_id:
            continue
        if σ.get("distilled_into"):
            continue
        text = str(σ.get("correct") or σ.get("text") or σ.get("cond") or sid)
        triggers = _triggers_from_text(cond or text)
        leaf_id = str(σ.get("leaf_id") or "")
        if leaf_id and leaf_id not in triggers:
            triggers.append(leaf_id)
        entry = {
            "id": key,
            "name": text[:72],
            "version": 1,
            "usage_count": 0,
            "status": "active",
            "triggers": triggers,
            "derived_from": [sid],
            "history": [{"event": "distill", "from": sid}],
        }
        body = (
            f"# Skill from Σ `{sid}`\n\n"
            f"kind: {kind}\nconf: {conf}\n\n"
            f"{text}\n"
        )
        _write_skill_files(workdir, entry, body)
        by_id[key] = entry
        created.append(entry)
        σ2 = dict(σ)
        σ2["distilled_into"] = key
        save_active_record(workdir, σ2)
        if len(created) >= limit:
            break
    if created:
        save_index(workdir, list(by_id.values()))
    return created

def _triggers_from_text(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_]{3,}", text.lower())
    out: list[str] = []
    for w in words:
        if w not in out:
            out.append(w)
        if len(out) >= 8:
            break
    return out

def match_skills(
    workdir: Path,
    *,
    leaf_id: str = "",
    title: str = "",
    acceptance: Sequence[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return active skills whose triggers match the current leaf/goal context."""
    hay = " ".join(
        [
            leaf_id.lower(),
            title.lower(),
            " ".join(str(a).lower() for a in (acceptance or [])),
        ]
    )
    matched: list[dict[str, Any]] = []
    for it in load_index(workdir):
        if it.get("status") != "active":
            continue
        triggers = [str(t).lower() for t in (it.get("triggers") or []) if t]
        if not triggers:
            continue
        if any(t in hay or (leaf_id and t == leaf_id.lower()) for t in triggers):
            matched.append(it)
        if len(matched) >= limit:
            break
    return matched

def render_learned_skills_block(skills: Sequence[Mapping[str, Any]]) -> str:
    if not skills:
        return ""
    lines = ["[LEARNED SKILLS]"]
    for sk in skills:
        lines.append(f"- {sk.get('id')}: {sk.get('name')}")
        hist = sk.get("history") or []
        if isinstance(hist, list) and hist:
            note = hist[-1]
            if isinstance(note, dict) and note.get("note"):
                lines.append(f"  note: {note['note']}")
    lines.append("Apply these skills when relevant; do not invent conflicting shortcuts.")
    return "\n".join(lines)

def revise_skill(workdir: Path, skill_id: str, *, note: str) -> dict[str, Any] | None:
    items = load_index(workdir)
    for it in items:
        if it.get("id") != skill_id:
            continue
        it["version"] = int(it.get("version") or 1) + 1
        hist = list(it.get("history") or [])
        hist.append({"event": "revise", "note": note[:300]})
        it["history"] = hist[-20:]
        save_index(workdir, items)
        body = (
            f"# {it.get('name')}\n\n"
            f"version: {it.get('version')}\n\n"
            f"## Latest revision\n\n{note}\n"
        )
        _write_skill_files(workdir, it, body)
        return it
    return None

def deprecate(workdir: Path, skill_id: str, *, reason: str = "") -> dict[str, Any] | None:
    items = load_index(workdir)
    for it in items:
        if it.get("id") != skill_id:
            continue
        it["status"] = "deprecated"
        hist = list(it.get("history") or [])
        hist.append({"event": "deprecate", "note": reason[:200]})
        it["history"] = hist[-20:]
        src = _skill_dir(workdir, skill_id)
        arch = skills_root(workdir) / "archived" / src.name
        arch.mkdir(parents=True, exist_ok=True)
        (arch / "meta.json").write_text(
            json.dumps(it, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (arch / "SKILL.md").write_text(
            f"# Deprecated · {it.get('name')}\n\n{reason}\n", encoding="utf-8"
        )
        save_index(workdir, items)
        return it
    return None

def deconstruct(
    workdir: Path,
    skill_id: str,
    *,
    parts: list[str],
) -> list[dict[str, Any]]:
    """Split one skill into child skills (K deconstruct)."""
    items = load_index(workdir)
    parent = next((it for it in items if it.get("id") == skill_id), None)
    if parent is None or not parts:
        return []
    created: list[dict[str, Any]] = []
    children_ids: list[str] = list(parent.get("children") or [])
    for i, part in enumerate(parts, start=1):
        cid = f"{skill_id}.part{i}"
        entry = {
            "id": cid,
            "name": str(part)[:72],
            "version": 1,
            "usage_count": 0,
            "status": "active",
            "triggers": list(parent.get("triggers") or []),
            "parent": skill_id,
            "derived_from": list(parent.get("derived_from") or []),
            "history": [{"event": "deconstruct", "from": skill_id}],
        }
        body = f"# {entry['name']}\n\nDeconstructed from `{skill_id}`.\n\n{part}\n"
        _write_skill_files(workdir, entry, body)
        items.append(entry)
        children_ids.append(cid)
        created.append(entry)
    parent["children"] = children_ids
    hist = list(parent.get("history") or [])
    hist.append({"event": "deconstruct", "into": children_ids})
    parent["history"] = hist[-20:]
    save_index(workdir, items)
    return created

def boundary_hints(workdir: Path, *, leaf_id: str = "", title: str = "") -> list[str]:
    """Return short boundary lines from active skills related to this leaf."""
    hints: list[str] = []
    for it in load_index(workdir):
        if it.get("status") != "active":
            continue
        triggers = [str(t) for t in (it.get("triggers") or []) if t]
        name = str(it.get("name") or "")
        if leaf_id and leaf_id in triggers:
            hints.append(f"skill {it.get('id')}: used {it.get('usage_count', 0)}× on {leaf_id}")
        elif title and title[:24] and title[:24].lower() in name.lower():
            hints.append(f"skill {it.get('id')}: related prior admit for similar goal")
        elif it.get("derived_from"):
            hints.append(f"skill {it.get('id')}: Σ-distilled — {name[:60]}")
    return hints[:5]
