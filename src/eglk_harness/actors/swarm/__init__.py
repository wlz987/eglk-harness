"""Phase-0 SWARM workers: Explorer / Verifier / Pruner — candidates/ only."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from eba import Worker

from eglk_harness.domain.adapters.base import AgentAdapter
from eglk_harness.domain.kernel.leaf_contract import contract_from_dict, LeafContract
from eglk_harness.domain.runtime.budgets import timeout_for_role
from eglk_harness.domain.runtime.bypass_llm import coerce_explorer, coerce_verifier, run_bypass_json
from eglk_harness.protocol import messages, payload, topics

def _write_candidate(loop_dir: Path, name: str, doc: dict[str, Any]) -> Path:
    from eglk_harness.domain.kernel.advisor_guard import advisor_write_guard

    cand = loop_dir / "candidates"
    cand.mkdir(parents=True, exist_ok=True)
    path = advisor_write_guard(loop_dir, cand / name)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path

def _leaf_ctx(args: Mapping[str, Any]) -> tuple[str, str, list[str], LeafContract | None]:
    leaf = str(args.get("subgoal_id") or "root")
    title = str(args.get("goal_title") or args.get("title") or leaf)
    criteria = [str(x) for x in (args.get("done_criteria") or []) if str(x).strip()]
    lc_raw = args.get("leaf_contract")
    contract: LeafContract | None = None
    if isinstance(lc_raw, dict):
        contract = contract_from_dict(lc_raw)
        if not contract.goal:
            contract.goal = title
        if not contract.acceptance:
            contract.acceptance = criteria
    return leaf, title, criteria, contract

def _leaf_block(
    leaf: str,
    title: str,
    criteria: Sequence[str],
    contract: LeafContract | None,
    *,
    audit: bool = False,
) -> str:
    if contract is not None:
        block = contract.render_maker_block()
    else:
        block = f"[LEAF]\nid: {leaf}\ntitle: {title}\nacceptance:\n" + "\n".join(
            f"  - {c}" for c in criteria
        )
    if audit:
        block = f"{block}\naudit: true"
    return block

def explorer_mechanical_enabled() -> bool:
    """Default mechanical Explorer (no LLM) — Gate never reads candidates."""
    raw = os.environ.get("EGLK_EXPLORER_MECHANICAL", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def explore_alternatives(title: str, criteria: Sequence[str]) -> list[dict[str, Any]]:
    """Leaf-aware mechanical alternatives (no LLM; Gate never reads these)."""
    alts: list[dict[str, Any]] = []
    if criteria:
        for i, c in enumerate(criteria[:5], start=1):
            alts.append(
                {
                    "id": f"alt-crit-{i}",
                    "text": f"Satisfy acceptance directly: {c}",
                    "prob": max(0.35, 0.9 - 0.08 * (i - 1)),
                    "impact": 0.85,
                }
            )
        alts.append(
            {
                "id": "alt-incremental",
                "text": f"Ship smallest verifiable slice of «{title}» then expand",
                "prob": 0.55,
                "impact": 0.7,
            }
        )
    else:
        alts = [
            {
                "id": "alt-direct",
                "text": f"Implement «{title}» against stated goal",
                "prob": 0.7,
                "impact": 0.8,
            },
            {
                "id": "alt-defer",
                "text": f"Defer «{title}» until prerequisites clear",
                "prob": 0.25,
                "impact": 0.2,
            },
        ]
    alts.append(
        {
            "id": "alt-low-value",
            "text": "Cosmetic rename without advancing acceptance",
            "prob": 0.1,
            "impact": 0.05,
        }
    )
    return alts

def verifier_challenges(title: str, criteria: Sequence[str], *, audit: bool) -> list[dict[str, Any]]:
    challenges: list[dict[str, Any]] = []
    for i, c in enumerate(criteria[:4], start=1):
        challenges.append(
            {
                "id": f"ch-acc-{i}",
                "title": f"Acceptance may be unmet: {c[:60]}",
                "text": f"Require concrete artifact proving: {c}",
            }
        )
    if not challenges:
        challenges.append(
            {
                "id": "ch-empty",
                "title": f"Empty or unproven deliverable for «{title}»",
                "text": "Ensure non-empty, inspectable artifacts exist",
            }
        )
    if audit:
        challenges.append(
            {
                "id": "ch-audit",
                "title": "Post-admit integrity",
                "text": "Confirm world mutations match Claim payload and Evidence",
            }
        )
    return challenges

class ExplorerActor(Worker):
    pattern = f"{topics.ROLE_EXPLORER_RUN}.*"
    result_prefix = topics.ROLE_EXPLORER_RESULT
    error_code = "explorer_failed"

    def __init__(self, *, adapter: AgentAdapter | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.adapter = adapter

    async def work(self, envelope_payload: Any) -> Any:
        args = payload.get_args(envelope_payload if isinstance(envelope_payload, dict) else {})
        loop_dir = Path(str(args["loop_dir"]))
        tick = int(args.get("tick", 0))
        leaf, title, criteria, contract = _leaf_ctx(args)
        workdir = Path(args.get("workdir") or loop_dir.parent.parent.parent).resolve()
        mech = explore_alternatives(title, criteria)
        leaf_block = _leaf_block(leaf, title, criteria, contract)
        raw: Any = None
        if not explorer_mechanical_enabled():
            try:
                raw = await run_bypass_json(
                    self.adapter,
                    role="explorer",
                    workdir=workdir,
                    leaf_block=leaf_block,
                    extra='JSON: {"alternatives":[{"id","text","prob","impact"}]}',
                    tick=tick,
                    subgoal_id=leaf,
                    timeout_s=float(args.get("timeout_s") or timeout_for_role("explorer")),
                )
            except Exception:
                # MCP/plugin misconfig or adapter faults must not abort the tick —
                # fall back to mechanical alternatives (Gate never reads Explorer).
                raw = None
        doc = coerce_explorer(raw, tick=tick, leaf=leaf, fallback=mech)
        doc["title"] = title
        _write_candidate(loop_dir, f"explorer_{tick:03d}.json", doc)
        return messages.ok_value(artifact=doc)

class VerifierActor(Worker):
    pattern = f"{topics.ROLE_VERIFIER_RUN}.*"
    result_prefix = topics.ROLE_VERIFIER_RESULT
    error_code = "verifier_failed"

    def __init__(self, *, audit: bool = False, adapter: AgentAdapter | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.audit = audit
        self.adapter = adapter

    async def work(self, envelope_payload: Any) -> Any:
        args = payload.get_args(envelope_payload if isinstance(envelope_payload, dict) else {})
        loop_dir = Path(str(args["loop_dir"]))
        tick = int(args.get("tick", 0))
        leaf, title, criteria, contract = _leaf_ctx(args)
        is_audit = bool(args.get("veto_audit") or self.audit)
        workdir = Path(args.get("workdir") or loop_dir.parent.parent.parent).resolve()
        mech = verifier_challenges(title, criteria, audit=is_audit)
        leaf_block = _leaf_block(leaf, title, criteria, contract, audit=is_audit)
        try:
            raw = await run_bypass_json(
                self.adapter,
                role="verifier",
                workdir=workdir,
                leaf_block=leaf_block,
                extra='JSON: {"challenges":[{"id","title","text"}],"veto":false}',
                tick=tick,
                subgoal_id=leaf,
                timeout_s=float(args.get("timeout_s") or timeout_for_role("verifier")),
            )
        except Exception:
            raw = None
        doc = coerce_verifier(raw, tick=tick, leaf=leaf, fallback=mech, audit=is_audit)
        doc["title"] = title
        name = f"verifier_audit_{tick:03d}.json" if is_audit else f"verifier_{tick:03d}.json"
        _write_candidate(loop_dir, name, doc)
        return messages.ok_value(artifact=doc)

class CandidateSelectorActor(Worker):
    """Mechanical candidate filter (design: CandidateSelector; wire topic remains pruner)."""

    pattern = f"{topics.ROLE_PRUNER_RUN}.*"
    result_prefix = topics.ROLE_PRUNER_RESULT
    error_code = "candidate_selector_failed"

    def __init__(self, *, adapter: AgentAdapter | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.adapter = adapter  # reserved; selection stays mechanical

    async def work(self, envelope_payload: Any) -> Any:
        args = payload.get_args(envelope_payload if isinstance(envelope_payload, dict) else {})
        loop_dir = Path(str(args["loop_dir"]))
        tick = int(args.get("tick", 0))
        explorer_path = loop_dir / "candidates" / f"explorer_{tick:03d}.json"
        alts: list[dict[str, Any]] = []
        if explorer_path.is_file():
            raw = json.loads(explorer_path.read_text(encoding="utf-8"))
            for a in raw.get("alternatives") or []:
                if not isinstance(a, dict):
                    continue
                score = float(a.get("prob", 0)) * float(a.get("impact", 0))
                entry = dict(a)
                entry["score"] = score
                entry["pruned"] = score < 0.2
                alts.append(entry)
        doc = {
            "role": "candidate_selector",
            "tick": tick,
            "alternatives": alts,
            "source": "mechanical",
        }
        _write_candidate(loop_dir, f"candidate_selector_{tick:03d}.json", doc)
        return messages.ok_value(artifact=doc)


class PrunerActor(CandidateSelectorActor):
    """Backward-compatible alias for CandidateSelectorActor."""

    error_code = "pruner_failed"
