"""Skill library K under ``.eglk-harness/memory/skills/``."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain import paths, sigma


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
        f"# {found.get('name')}\n\n"
        f"Leaf skill reinforced on admit (tick={tick}).\n\n"
        f"- triggers: {', '.join(str(t) for t in found.get('triggers') or [])}\n"
        f"- usage_count: {found.get('usage_count')}\n"
        f"- last_note: {note or '(none)'}\n"
    )
    _write_skill_files(workdir, found, body)
    return found


def distill_from_sigma(
    workdir: Path,
    *,
    min_conf: float = 0.65,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Promote high-confidence Σ hits/lessons into K skills (derived_from σ id)."""
    active = sigma.load_active(workdir)
    items = load_index(workdir)
    by_id = {str(it.get("id")): it for it in items}
    created: list[dict[str, Any]] = []
    for σ in active:
        if not isinstance(σ, Mapping):
            continue
        conf = float(σ.get("conf") or 0)
        kind = str(σ.get("kind") or "")
        if conf < min_conf or kind not in {"hit", "lesson"}:
            continue
        sid = str(σ.get("id") or "")
        if not sid:
            continue
        key = f"sigma:{sid}"
        if key in by_id:
            continue
        if σ.get("distilled_into"):
            continue
        text = str(σ.get("text") or σ.get("cond") or sid)
        entry = {
            "id": key,
            "name": text[:72],
            "version": 1,
            "usage_count": 0,
            "status": "active",
            "triggers": [str(σ.get("leaf_id") or "")],
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
        # mark back on a copy in active
        σ2 = dict(σ)
        σ2["distilled_into"] = key
        # replace in active list
        for i, old in enumerate(active):
            if isinstance(old, dict) and str(old.get("id")) == sid:
                active[i] = σ2
                break
        if len(created) >= limit:
            break
    if created:
        save_index(workdir, list(by_id.values()))
        sigma.save_active(workdir, [x for x in active if isinstance(x, dict)])
    return created


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
        # move files to archived/
        src = _skill_dir(workdir, skill_id)
        arch = skills_root(workdir) / "archived" / src.name
        arch.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir() and src != arch:
            for child in src.iterdir():
                dest = arch / child.name
                dest.write_bytes(child.read_bytes())
                child.unlink(missing_ok=True)
            try:
                src.rmdir()
            except OSError:
                pass
            _write_skill_files(
                workdir,
                {**it, "id": skill_id},
                f"# Deprecated\n\n{reason}\n",
            )
            # write under archived explicitly
            arch.mkdir(parents=True, exist_ok=True)
            (arch / "meta.json").write_text(
                json.dumps(it, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            (arch / "SKILL.md").write_text(f"# Deprecated\n\n{reason}\n", encoding="utf-8")
        save_index(workdir, items)
        return it
    return None


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
