"""Advisor helpers — write candidates/ only; never append events.

Governor / Explorer / Verifier / CandidateSelector / Refiner produce candidate
commands or files under ``candidates/``. CommandHandler is the sole path that
may turn a validated split/amendment candidate into events.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.governor_split import propose_children
from eglk_harness.domain.kernel.reducer import ProjectionState
from eglk_harness.domain.kernel.scheduler import advisor_plan, pick_sibling_merge_pair, ready_pool
from eglk_harness.domain.kernel.swarm import decide_swarm


@dataclass(frozen=True)
class AliveCandidate:
    path: Path
    role: str
    score: float
    payload: dict[str, Any]
    pruned: bool = False


def candidates_dir(loop_dir: Path) -> Path:
    d = Path(loop_dir) / "candidates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def count_candidates(loop_dir: Path) -> int:
    d = Path(loop_dir) / "candidates"
    if not d.is_dir():
        return 0
    return sum(1 for p in d.glob("*.json") if p.is_file() and not p.name.endswith(".pruned.json"))


def _score(payload: Mapping[str, Any]) -> float:
    """Mechanical CandidateSelector key: max(prob × impact) over alternatives."""
    alts = payload.get("alternatives") or payload.get("challenges") or []
    best = 0.0
    if isinstance(alts, list):
        for a in alts:
            if not isinstance(a, Mapping):
                continue
            try:
                prob = float(a.get("prob", a.get("confidence", 0.5)) or 0.5)
                impact = float(a.get("impact", a.get("severity", 0.5)) or 0.5)
            except (TypeError, ValueError):
                prob, impact = 0.5, 0.5
            best = max(best, prob * impact)
    if best > 0:
        return best
    try:
        return float(payload.get("score") or payload.get("conf") or 0.5)
    except (TypeError, ValueError):
        return 0.5


def list_alive_candidates(loop_dir: Path) -> list[AliveCandidate]:
    d = Path(loop_dir) / "candidates"
    if not d.is_dir():
        return []
    out: list[AliveCandidate] = []
    for p in sorted(d.glob("*.json")):
        if p.name.endswith(".pruned.json"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("pruned") is True:
            continue
        role = str(data.get("role") or p.stem.split("_")[0] or "unknown")
        out.append(AliveCandidate(path=p, role=role, score=_score(data), payload=data))
    return out


def run_candidate_selector(loop_dir: Path, *, keep_max: int | None = None) -> dict[str, Any]:
    """Prune lowest-scoring candidates when backlog exceeds CANDIDATES_MAX."""
    keep = int(keep_max if keep_max is not None else P.CANDIDATES_MAX)
    alive = list_alive_candidates(loop_dir)
    if len(alive) <= keep:
        return {"pruned": 0, "kept": len(alive), "forced": False}
    ranked = sorted(alive, key=lambda c: (-c.score, c.path.name))
    keep_set = {c.path for c in ranked[:keep]}
    pruned = 0
    for c in ranked[keep:]:
        data = dict(c.payload)
        data["pruned"] = True
        data["prune_reason"] = "candidate_selector_score"
        c.path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        # also drop visibility via rename marker
        marker = c.path.with_name(c.path.stem + ".pruned.json")
        try:
            c.path.rename(marker)
        except OSError:
            pass
        pruned += 1
    return {"pruned": pruned, "kept": keep, "forced": True}


def write_explorer_candidate(
    loop_dir: Path,
    *,
    step: int,
    node_id: str,
    alternatives: Sequence[Mapping[str, Any]] | None = None,
) -> Path:
    payload = {
        "role": "explorer",
        "node_id": node_id,
        "step": step,
        "alternatives": list(alternatives)
        or [
            {"id": "alt-1", "text": "direct implement", "prob": 0.8, "impact": 0.9},
            {"id": "alt-2", "text": "incremental", "prob": 0.5, "impact": 0.6},
            {"id": "alt-3", "text": "minimal patch", "prob": 0.3, "impact": 0.4},
        ],
    }
    path = candidates_dir(loop_dir) / f"explorer_{step:03d}_{_safe(node_id)}.json"
    from eglk_harness.domain.kernel.advisor_guard import advisor_write_guard

    path = advisor_write_guard(loop_dir, path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_verifier_candidate(
    loop_dir: Path,
    *,
    step: int,
    node_id: str,
    challenges: Sequence[Mapping[str, Any]] | None = None,
    repair_reason: str | None = None,
) -> Path:
    payload = {
        "role": "verifier",
        "node_id": node_id,
        "step": step,
        "repair_reason": repair_reason,
        "challenges": list(challenges)
        or [
            {
                "id": "ch-1",
                "title": "missing artifact",
                "text": "ensure deliverable exists and is attested",
                "severity": 0.8,
                "prob": 0.7,
            }
        ],
        "veto": False,
    }
    path = candidates_dir(loop_dir) / f"verifier_{step:03d}_{_safe(node_id)}.json"
    from eglk_harness.domain.kernel.advisor_guard import advisor_write_guard

    path = advisor_write_guard(loop_dir, path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def build_mechanical_split_candidate(
    state: ProjectionState,
    node_id: str,
    *,
    step: int = 0,
) -> dict[str, Any] | None:
    """Build a CoverageProof-bearing split candidate for CommandHandler."""
    node = state.nodes.get(node_id)
    if node is None:
        return None
    parent_obs = list(node.obligation_refs)
    if not parent_obs:
        parent_obs = [oid for oid, ob in state.obligations.items() if ob.origin == "root"]
    if not parent_obs:
        return None

    # Prefer statements from obligation ledger for done_criteria
    criteria: list[str] = []
    for oid in parent_obs:
        ob = state.obligations.get(oid)
        if ob and ob.statement:
            criteria.append(ob.statement)
    if not criteria:
        criteria = [node.title or node_id]

    children_raw = propose_children(
        node_id, node.title or node_id, criteria, repair_streak=node.repair_streak
    )
    # Assign obligations: partition when enough parent obs; else refinement
    child_obligation_map: dict[str, list[str]] = {}
    opened: list[dict[str, Any]] = []
    proof_kind = "partition" if len(parent_obs) >= len(children_raw) else "refinement"

    if proof_kind == "partition":
        for i, ch in enumerate(children_raw):
            oid = parent_obs[i] if i < len(parent_obs) else parent_obs[-1]
            child_obligation_map[ch["id"]] = [oid]
            # leftover parent obs go to last child
        if len(parent_obs) > len(children_raw):
            last = children_raw[-1]["id"]
            child_obligation_map[last] = list(parent_obs[len(children_raw) - 1 :])
    else:
        for i, ch in enumerate(children_raw, start=1):
            derived_ids: list[str] = []
            for j, poid in enumerate(parent_obs, start=1):
                did = f"{poid}.{i:02d}" if len(parent_obs) > 1 else f"{poid}.{i:02d}"
                if len(parent_obs) == 1:
                    did = f"{parent_obs[0]}.{i:02d}"
                else:
                    did = f"{poid}.c{i:02d}"
                parent_ob = state.obligations.get(poid)
                opened.append(
                    {
                        "id": did,
                        "requirement_id": parent_ob.requirement_id if parent_ob else "req-1",
                        "parent_obligation_id": poid,
                        "statement": (
                            ch["done_criteria"][0]
                            if ch.get("done_criteria")
                            else (parent_ob.statement if parent_ob else ch["title"])
                        ),
                        "verification_type": (
                            parent_ob.verification_type if parent_ob else "custom_attestation"
                        ),
                        "status": "open",
                        "origin": "derived",
                    }
                )
                derived_ids.append(did)
                # one derived per parent for this child is enough when single parent
                if len(parent_obs) == 1:
                    break
            child_obligation_map[ch["id"]] = derived_ids

    children = []
    for ch in children_raw:
        children.append(
            {
                "id": ch["id"],
                "title": ch["title"],
                "obligation_refs": list(child_obligation_map.get(ch["id"]) or []),
                "done_criteria": list(ch.get("done_criteria") or []),
                "depth": node.depth + 1,
            }
        )

    depends_on: list[dict[str, str]] = []
    if proof_kind == "refinement" and len(children_raw) >= 2:
        from eglk_harness.domain.kernel.projection_view import split_depends_on_chain

        depends_on = split_depends_on_chain([ch["id"] for ch in children_raw])

    return {
        "role": "governor",
        "step": step,
        "source": "mechanical",
        "split_node": node_id,
        "repair_streak": node.repair_streak,
        "children": children,
        "opened_obligations": opened,
        "depends_on": depends_on,
        "coverage_proof": {
            "parent_obligation_ids": parent_obs,
            "child_obligation_map": child_obligation_map,
            "proof_kind": proof_kind,
        },
    }


def build_mechanical_merge_candidate(
    state: ProjectionState,
    *,
    step: int = 0,
    min_criteria_sim: float = 0.5,
) -> dict[str, Any] | None:
    """Build merge payload for CommandHandler when sibling criteria overlap."""
    pair = pick_sibling_merge_pair(state, min_criteria_sim=min_criteria_sim)
    if pair is None:
        return None
    parent_id, node_ids, score = pair
    merged_refs: list[str] = []
    for nid in node_ids:
        node = state.nodes.get(nid)
        if node is not None:
            merged_refs.extend(node.obligation_refs)
    merged_refs = list(dict.fromkeys(merged_refs))
    into = f"{parent_id}.m{step:03d}"
    return {
        "role": "governor",
        "step": step,
        "source": "mechanical",
        "into": into,
        "node_ids": node_ids,
        "parent_id": parent_id,
        "title": f"merged:{'+'.join(node_ids)}",
        "obligation_refs": merged_refs,
        "reason": f"criteria_overlap {score:.2f}",
        "score": score,
    }


def write_governor_merge_candidate(loop_dir: Path, candidate: Mapping[str, Any], *, step: int) -> Path:
    into = str(candidate.get("into") or "merged")
    path = candidates_dir(loop_dir) / f"governor_merge_{step:03d}_{_safe(into)}.json"
    path.write_text(json.dumps(dict(candidate), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_governor_split_candidate(loop_dir: Path, candidate: Mapping[str, Any], *, step: int) -> Path:
    node_id = str(candidate.get("split_node") or "node")
    path = candidates_dir(loop_dir) / f"governor_split_{step:03d}_{_safe(node_id)}.json"
    path.write_text(json.dumps(dict(candidate), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def should_trigger_governor(state: ProjectionState, *, node_id: str | None = None) -> tuple[bool, str]:
    """Return (trigger, reason) for Governor advisor."""
    if node_id and node_id in state.nodes:
        if state.nodes[node_id].repair_streak >= P.SPLIT_REPAIR_STREAK:
            return True, "repair_streak"
    pool = ready_pool(state)
    if not pool:
        # tree not closed and no ready work → structural stuck
        if state.run_status == "running":
            open_obs = [o for o in state.obligations.values() if o.status in {"open", "invalidated"}]
            if open_obs:
                return True, "ready_pool_empty"
    # defect_suspected is checked by caller from last evidence
    return False, ""


def plan_session_advisors(
    state: ProjectionState,
    loop_dir: Path,
    *,
    swarm_soft: str | None = None,
    last_repair_reason: str | None = None,
) -> dict[str, bool]:
    """Combine scheduler.advisor_plan + swarm.decide_swarm."""
    base = advisor_plan(state, candidates_count=count_candidates(loop_dir), swarm_soft=swarm_soft)
    swarm = decide_swarm(
        candidate_count=count_candidates(loop_dir),
        cognitive_tokens=state.cognitive_tokens,
        cognitive_tokens_max=state.cognitive_tokens_max,
        soft=swarm_soft,
        last_repair_reason=last_repair_reason,
    )
    return {
        "governor": bool(base.get("governor")),
        "explorer": bool(swarm.explorer and base.get("explorer", True)),
        "verifier": bool(swarm.verifier),
        "candidate_selector": bool(swarm.candidate_selector or base.get("candidate_selector")),
        "refiner": bool(base.get("refiner")),
    }


def alive_candidate_summary(loop_dir: Path, *, limit: int = 5) -> str:
    """Short Maker-visible summary of surviving candidates (not full dumps)."""
    alive = sorted(list_alive_candidates(loop_dir), key=lambda c: (-c.score, c.path.name))
    if not alive:
        return "(no alive candidates)"
    lines = []
    for c in alive[:limit]:
        lines.append(f"- [{c.role}] score={c.score:.2f} file={c.path.name}")
    return "\n".join(lines)


def _safe(node_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", node_id)[:64]
