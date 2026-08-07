"""Optional LLM episodes for bypass roles (Governor/SWARM/Refiner/compile).

Tools/MCP are always forbidden. On parse failure → one format-repair try → None
(callers apply mechanical fallback).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.adapters.base import AgentAdapter, EpisodeRequest
from eglk_harness.domain.runtime.json_extract import extract_json
from eglk_harness.domain.runtime.models import resolve_model
from eglk_harness.domain.memory.skills import render_prompt


def bypass_llm_enabled(
    adapter: AgentAdapter | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> bool:
    """``EGLK_BYPASS_LLM``: ``1`` force; ``0`` mechanical; ``auto`` = live backends only."""
    env = env or os.environ
    raw = (env.get("EGLK_BYPASS_LLM") or "auto").strip().lower()
    if raw in {"0", "off", "false", "no", "mechanical"}:
        return False
    if raw in {"1", "on", "true", "yes", "llm"}:
        return True
    # auto: skip mock/fake so unit/integration stay deterministic
    if adapter is None:
        return False
    name = getattr(adapter, "name", "") or ""
    return name not in {"mock", "fake"}


def _parse_bypass_result(result: Any) -> dict[str, Any] | None:
    if isinstance(getattr(result, "parsed", None), dict):
        return result.parsed
    text = getattr(result, "text", None) or ""
    if not str(text).strip():
        return None
    try:
        doc = extract_json(text)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


async def run_bypass_json(
    adapter: AgentAdapter | None,
    *,
    role: str,
    workdir: Path,
    leaf_block: str,
    extra: str = "",
    tick: int = 0,
    subgoal_id: str = "root",
    timeout_s: float = 120.0,
    force: bool = False,
    tee_path: str | None = None,
    repair: bool = True,
) -> dict[str, Any] | None:
    """Run a no-tools Adapter episode; return parsed JSON object or None.

    ``force=True`` ignores ``EGLK_BYPASS_LLM`` auto-skip (STEP0 compile / soak).
    On unparseable output, optionally retries once with a format-repair prompt.
    """
    if adapter is None:
        return None
    if not force and not bypass_llm_enabled(adapter):
        return None

    prompt = render_prompt(role, leaf_block=leaf_block, extra=extra)
    from eglk_harness.domain.runtime.prompt_i18n import constraint_block

    prompt = f"{prompt}\n\n{constraint_block()}"
    req = EpisodeRequest(
        role=role,
        prompt=prompt,
        workdir=workdir,
        tools_allowed=False,
        expect="text",
        model=resolve_model(role),
        timeout_s=timeout_s,
        meta={"tick": tick, "subgoal_id": subgoal_id, "bypass": True},
        tee_path=tee_path,
    )
    result = await adapter.run_episode(req)
    doc = _parse_bypass_result(result)
    if doc is not None:
        return doc
    if not repair:
        return None

    err = getattr(result, "error", None) or "unparseable_bypass_json"
    repair_extra = (
        f"{extra}\n\nFORMAT REPAIR: previous output failed ({err}). "
        "Return a single JSON object only — no markdown fences, no prose."
    )
    if getattr(result, "text", None):
        repair_extra += f"\nPrevious (truncated):\n```\n{(result.text or '')[:1500]}\n```\n"
    repair_prompt = render_prompt(role, leaf_block=leaf_block, extra=repair_extra)
    repair_tee = None
    if tee_path:
        p = Path(tee_path)
        repair_tee = str(p.with_name(p.stem + "_repair" + p.suffix))
    result2 = await adapter.run_episode(
        EpisodeRequest(
            role=role,
            prompt=repair_prompt,
            workdir=workdir,
            tools_allowed=False,
            expect="text",
            model=resolve_model(role),
            timeout_s=min(float(timeout_s), 180.0),
            meta={"tick": tick, "subgoal_id": subgoal_id, "bypass": True, "format_repair": True},
            tee_path=repair_tee,
        )
    )
    return _parse_bypass_result(result2)


def coerce_governor_proposal(
    raw: Mapping[str, Any] | None,
    *,
    tick: int,
    leaf_id: str,
    fallback: Mapping[str, Any],
) -> dict[str, Any]:
    if not raw:
        return dict(fallback)
    children = raw.get("children")
    if not isinstance(children, list) or len(children) < 2:
        return dict(fallback)
    out_children: list[dict[str, Any]] = []
    for i, c in enumerate(children, start=1):
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or f"{leaf_id}.{i:02d}")
        title = str(c.get("title") or cid)
        crit = c.get("done_criteria") or c.get("acceptance") or []
        if not isinstance(crit, list) or not crit:
            continue
        out_children.append(
            {
                "id": cid,
                "title": title,
                "done_criteria": [str(x) for x in crit if str(x).strip()],
            }
        )
    if len(out_children) < 2:
        return dict(fallback)
    return {
        "role": "governor",
        "tick": tick,
        "split_node": str(raw.get("split_node") or leaf_id),
        "children": out_children,
        "source": "llm",
    }


def _safe_unit_float(val: Any, default: float = 0.5) -> float:
    """Best-effort [0,1]-ish float from LLM drift (numbers or qualitative strings)."""
    if isinstance(val, bool):
        return default
    if isinstance(val, (int, float)):
        return max(0.0, min(1.0, float(val)))
    if isinstance(val, str):
        s = val.strip().lower()
        try:
            return max(0.0, min(1.0, float(s)))
        except ValueError:
            pass
        # Qualitative buckets seen in live Explorer output
        if any(k in s for k in ("highest", "high", "strong", "critical")):
            return 0.85
        if any(k in s for k in ("medium", "moderate", "mid")):
            return 0.55
        if any(k in s for k in ("low", "minor", "weak", "decoy")):
            return 0.2
    return default


def coerce_explorer(raw: Mapping[str, Any] | None, *, tick: int, leaf: str, fallback: list) -> dict[str, Any]:
    if not raw:
        return {"role": "explorer", "tick": tick, "leaf_id": leaf, "alternatives": fallback, "source": "mechanical"}
    alts = raw.get("alternatives")
    if not isinstance(alts, list) or not alts:
        return {"role": "explorer", "tick": tick, "leaf_id": leaf, "alternatives": fallback, "source": "mechanical"}
    clean = []
    for i, a in enumerate(alts, start=1):
        if not isinstance(a, dict):
            continue
        text = a.get("text") or a.get("name") or a.get("title") or a.get("description") or ""
        if a.get("description") and a.get("name") and not a.get("text"):
            text = f"{a.get('name')}: {a.get('description')}"
        clean.append(
            {
                "id": str(a.get("id") or f"alt-{i}"),
                "text": str(text).strip() or f"alternative-{i}",
                "prob": _safe_unit_float(a.get("prob"), 0.5),
                "impact": _safe_unit_float(a.get("impact"), 0.5),
            }
        )
    if not clean:
        return {"role": "explorer", "tick": tick, "leaf_id": leaf, "alternatives": fallback, "source": "mechanical"}
    return {
        "role": "explorer",
        "tick": tick,
        "leaf_id": leaf,
        "title": raw.get("title"),
        "alternatives": clean,
        "source": "llm",
    }


def coerce_verifier(
    raw: Mapping[str, Any] | None,
    *,
    tick: int,
    leaf: str,
    fallback: list,
    audit: bool,
) -> dict[str, Any]:
    role = "verifier_audit" if audit else "verifier"
    if not raw:
        return {"role": role, "tick": tick, "leaf_id": leaf, "challenges": fallback, "veto": False, "source": "mechanical"}
    ch = raw.get("challenges")
    if not isinstance(ch, list) or not ch:
        return {"role": role, "tick": tick, "leaf_id": leaf, "challenges": fallback, "veto": False, "source": "mechanical"}
    clean = []
    for i, c in enumerate(ch, start=1):
        if not isinstance(c, dict):
            continue
        clean.append(
            {
                "id": str(c.get("id") or f"ch-{i}"),
                "title": str(c.get("title") or c.get("text") or ""),
                "text": str(c.get("text") or c.get("title") or ""),
            }
        )
    if not clean:
        return {"role": role, "tick": tick, "leaf_id": leaf, "challenges": fallback, "veto": False, "source": "mechanical"}
    return {
        "role": role,
        "tick": tick,
        "leaf_id": leaf,
        "challenges": clean,
        "veto": bool(raw.get("veto", False)),
        "source": "llm",
    }


def coerce_refiner(raw: Mapping[str, Any] | None, *, fallback: Mapping[str, Any]) -> dict[str, Any]:
    if not raw or not raw.get("id"):
        return dict(fallback)
    item = dict(fallback)
    item.update({k: v for k, v in raw.items() if k in {"id", "kind", "text", "cond", "conf", "leaf_id", "gaps", "step_review"}})
    item["source"] = "llm"
    return item
