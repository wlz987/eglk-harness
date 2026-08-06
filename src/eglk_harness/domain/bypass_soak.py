"""Bypass-role LLM soak — exercise Governor/Explorer/Verifier/Refiner/compile.

Gate is never involved. Tools/MCP stay forbidden. Safe to run with ``--agent mock``
(``force``) or live Codex/Claude (``EGLK_SOAK_LIVE=1`` / ``--live``).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from eglk_harness.domain.adapters.base import AgentAdapter
from eglk_harness.domain.bypass_llm import (
    coerce_explorer,
    coerce_governor_proposal,
    coerce_refiner,
    coerce_verifier,
    run_bypass_json,
)
from eglk_harness.domain.governor_split import proposal_document


SOAK_ROLES: tuple[str, ...] = ("governor", "explorer", "verifier", "refiner", "compile")


@dataclass
class SoakRoleResult:
    role: str
    ok: bool
    source: str  # llm | mechanical_fallback | error
    detail: str = ""
    elapsed_s: float = 0.0
    artifact: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SoakReport:
    agent: str
    workdir: str
    roles: list[SoakRoleResult] = field(default_factory=list)
    ok: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "workdir": self.workdir,
            "ok": self.ok,
            "roles": [r.to_dict() for r in self.roles],
        }


def _leaf_block(*, leaf_id: str = "root", title: str = "soak leaf") -> str:
    return (
        f"[LEAF]\nid: {leaf_id}\ntitle: {title}\n"
        "acceptance:\n  - hello.txt exists with non-empty content\n"
        "  - evidence is inspectable\n"
    )


async def soak_bypass_roles(
    adapter: AgentAdapter,
    workdir: Path,
    *,
    roles: tuple[str, ...] = SOAK_ROLES,
    timeout_s: float = 120.0,
    force: bool = True,
    write_report: bool = True,
) -> SoakReport:
    """Run each bypass role episode and coerce; record llm vs mechanical source."""
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    log_dir = workdir / ".eglk-harness" / "soak" / "bypass"
    log_dir.mkdir(parents=True, exist_ok=True)

    leaf = "root"
    title = "bypass soak leaf"
    leaf_block = _leaf_block(leaf_id=leaf, title=title)
    report = SoakReport(agent=getattr(adapter, "name", "unknown"), workdir=str(workdir))

    for role in roles:
        t0 = time.monotonic()
        tee = str(log_dir / f"{role}.jsonl")
        try:
            if role == "governor":
                fallback = proposal_document(
                    tick=0, leaf_id=leaf, title=title, done_criteria=["hello.txt exists"], repair_streak=2
                )
                raw = await run_bypass_json(
                    adapter,
                    role="governor",
                    workdir=workdir,
                    leaf_block=leaf_block,
                    extra='JSON: {"split_node","children":[{"id","title","done_criteria":[]}]}',
                    force=force,
                    tee_path=tee,
                    timeout_s=timeout_s,
                )
                art = coerce_governor_proposal(raw, tick=0, leaf_id=leaf, fallback=fallback)
                ok = len(art.get("children") or []) >= 2
                source = str(art.get("source") or ("llm" if raw else "mechanical_fallback"))
                detail = f"children={len(art.get('children') or [])}"
            elif role == "explorer":
                mech = [
                    {"id": "alt-1", "text": "direct", "prob": 0.7, "impact": 0.8},
                    {"id": "alt-2", "text": "incremental", "prob": 0.4, "impact": 0.5},
                ]
                raw = await run_bypass_json(
                    adapter,
                    role="explorer",
                    workdir=workdir,
                    leaf_block=leaf_block,
                    extra='JSON: {"alternatives":[{"id","text","prob","impact"}]}',
                    force=force,
                    tee_path=tee,
                    timeout_s=timeout_s,
                )
                art = coerce_explorer(raw, tick=0, leaf=leaf, fallback=mech)
                ok = bool(art.get("alternatives"))
                source = str(art.get("source") or "mechanical_fallback")
                detail = f"alts={len(art.get('alternatives') or [])}"
            elif role == "verifier":
                mech = [{"id": "ch-1", "title": "missing file", "text": "require hello.txt"}]
                raw = await run_bypass_json(
                    adapter,
                    role="verifier",
                    workdir=workdir,
                    leaf_block=leaf_block,
                    extra='JSON: {"challenges":[{"id","title","text"}],"veto":false}',
                    force=force,
                    tee_path=tee,
                    timeout_s=timeout_s,
                )
                art = coerce_verifier(raw, tick=0, leaf=leaf, fallback=mech, audit=False)
                ok = bool(art.get("challenges"))
                source = str(art.get("source") or "mechanical_fallback")
                detail = f"challenges={len(art.get('challenges') or [])}"
            elif role == "refiner":
                fallback = {
                    "id": "sigma-soak-001",
                    "kind": "hit",
                    "text": "mechanical fallback hit",
                    "conf": 0.5,
                }
                raw = await run_bypass_json(
                    adapter,
                    role="refiner",
                    workdir=workdir,
                    leaf_block="[REFINE]\ndecision: admit\nreason: soak\nleaf: root",
                    extra='JSON: {"id","kind","text","conf"}',
                    force=force,
                    tee_path=tee,
                    timeout_s=timeout_s,
                )
                art = coerce_refiner(raw, fallback=fallback)
                ok = bool(art.get("id"))
                source = str(art.get("source") or "mechanical_fallback")
                detail = f"kind={art.get('kind')}"
            elif role == "compile":
                raw = await run_bypass_json(
                    adapter,
                    role="compile",
                    workdir=workdir,
                    leaf_block="[GOAL.md]\n# Soak\n\n- [ ] hello.txt exists\n",
                    extra='JSON: {"title","direction","acceptance":[],"constraints":[],"notes"}',
                    force=force,
                    tee_path=tee,
                    timeout_s=timeout_s,
                )
                art = dict(raw or {})
                ok = bool(art.get("title") or art.get("acceptance"))
                source = "llm" if raw else "mechanical_fallback"
                # compile soak: mechanical frame still counts as ok if llm missing
                if not ok and not raw:
                    art = {"title": "Soak", "acceptance": ["hello.txt exists"], "source": "mechanical_fallback"}
                    ok = True
                    source = "mechanical_fallback"
                    detail = "fallback_frame"
                else:
                    detail = f"title={art.get('title')}"
            else:
                report.roles.append(
                    SoakRoleResult(role=role, ok=False, source="error", detail="unknown_role")
                )
                continue

            report.roles.append(
                SoakRoleResult(
                    role=role,
                    ok=ok,
                    source=source,
                    detail=detail,
                    elapsed_s=round(time.monotonic() - t0, 3),
                    artifact=art if isinstance(art, dict) else {},
                )
            )
            (log_dir / f"{role}.json").write_text(
                json.dumps(report.roles[-1].to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001 — soak must continue other roles
            report.roles.append(
                SoakRoleResult(
                    role=role,
                    ok=False,
                    source="error",
                    detail=str(exc)[:300],
                    elapsed_s=round(time.monotonic() - t0, 3),
                )
            )

    report.ok = all(r.ok for r in report.roles) and bool(report.roles)
    if write_report:
        (log_dir / "report.json").write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return report
