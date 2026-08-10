"""Refiner actor — writes sigma/refined/ only; never touches Gate inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eba import Worker

from eglk_harness.domain.memory import sigma
from eglk_harness.domain.adapters.base import AgentAdapter
from eglk_harness.domain.runtime.budgets import timeout_for_role
from eglk_harness.domain.runtime.bypass_llm import coerce_refiner, run_bypass_json
from eglk_harness.protocol import messages, payload, topics

def _step_bits(claim: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(claim, Mapping):
        return {}
    sr = claim.get("step_review")
    if not isinstance(sr, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("gains", "losses", "benefits", "risks"):
        val = sr.get(key)
        if isinstance(val, list) and val:
            out[key] = [str(x) for x in val[:4]]
    return out

def _gap_bits(evidence: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(evidence, Mapping):
        return []
    gaps = evidence.get("gaps") or []
    if not isinstance(gaps, list):
        return []
    texts: list[str] = []
    for g in gaps[:6]:
        if isinstance(g, dict):
            texts.append(str(g.get("text") or g.get("title") or g))
        else:
            texts.append(str(g))
    return texts

class RefinerActor(Worker):
    pattern = f"{topics.ROLE_REFINER_RUN}.*"
    result_prefix = topics.ROLE_REFINER_RESULT
    error_code = "refiner_failed"

    def __init__(self, *, adapter: AgentAdapter | None = None, **kwargs: Any) -> None:
        if kwargs.pop("mcp_config", None) or kwargs.pop("add_dirs", None):
            raise AssertionError("Refiner must not receive MCP")
        if kwargs.pop("tools_allowed", False):
            raise AssertionError("Refiner tools_allowed must be False")
        super().__init__(**kwargs)
        self.adapter = adapter

    async def work(self, envelope_payload: Any) -> Any:
        args = payload.get_args(envelope_payload if isinstance(envelope_payload, dict) else {})
        loop_dir = Path(str(args["loop_dir"]))
        tick = int(args.get("tick", 0))
        decision = str(args.get("decision") or "")
        reason = str(args.get("reason") or "")
        leaf = str(args.get("subgoal_id") or "")
        claim = args.get("claim") if isinstance(args.get("claim"), dict) else None
        evidence = args.get("evidence") if isinstance(args.get("evidence"), dict) else None
        step = _step_bits(claim)
        gaps = _gap_bits(evidence)
        workdir = Path(args.get("workdir") or loop_dir.parent.parent.parent).resolve()

        if decision == "abort":
            fallback: dict[str, Any] = {
                "id": f"sigma-abort-{tick:03d}",
                "kind": "archive",
                "decision": decision,
                "reason": reason,
                "leaf_id": leaf,
                "conf": 0.5,
            }
        elif decision == "repair":
            text = f"repair:{reason}"
            if gaps:
                text = f"{text}; gaps: {'; '.join(gaps[:2])}"
            fallback = {
                "id": f"sigma-lesson-{tick:03d}",
                "kind": "lesson",
                "cond": reason,
                "text": text,
                "leaf_id": leaf,
                "gaps": gaps,
                "step_review": step,
                "conf": 0.6,
            }
        else:
            benefit = ""
            if step.get("benefits"):
                benefit = str(step["benefits"][0])
            fallback = {
                "id": f"sigma-hit-{tick:03d}",
                "kind": "hit",
                "text": benefit or "admit reinforced",
                "leaf_id": leaf,
                "step_review": step,
                "conf": 0.7,
            }

        leaf_block = (
            f"[REFINE]\ndecision: {decision}\nreason: {reason}\nleaf: {leaf}\n"
            f"gaps: {gaps}\nstep_review: {step}"
        )
        raw = await run_bypass_json(
            self.adapter,
            role="refiner",
            workdir=workdir,
            leaf_block=leaf_block,
            extra='JSON: {"id","kind","text","conf"}',
            tick=tick,
            subgoal_id=leaf or "root",
            timeout_s=float(args.get("timeout_s") or timeout_for_role("refiner")),
        )
        item = coerce_refiner(raw, fallback=fallback)
        path = sigma.write_refined(loop_dir, tick, item)

        # Σ-similarity merge suggestions for next tick (CommandHandler.commit_merge at tick begin)
        from eglk_harness.domain.kernel.projection_replay import projection_state_from_loop
        from eglk_harness.domain.memory.sigma_merge import suggest_sibling_merges

        state = projection_state_from_loop(loop_dir)
        suggestions = suggest_sibling_merges(state, sigma.load_active(workdir))
        if suggestions:
            cand = loop_dir / "candidates"
            cand.mkdir(parents=True, exist_ok=True)
            for i, sug in enumerate(suggestions[:3]):
                sug_path = cand / f"merge_suggest_{tick:03d}_{i}.json"
                sug = dict(sug)
                sug["into"] = f"{sug.get('parent_id')}.ms{tick:03d}{i}"
                sug_path.write_text(
                    json.dumps(sug, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

        return messages.ok_value(refined=item, path=str(path))
