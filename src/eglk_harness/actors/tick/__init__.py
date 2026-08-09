"""TickJob — Phase 0 SWARM → Phase 1 main chain → Phase 2 refine/veto → Phase 3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eba import ErrBody, OkBody, is_result_err, is_result_ok, result_error, result_value
from eba_job import Job

from eglk_harness.domain.kernel import integrity
from eglk_harness.domain.kernel import loop_store
from eglk_harness.domain.memory import phase3
from eglk_harness.domain.memory import sigma
from eglk_harness.domain.memory import skill_lib
from eglk_harness.domain.kernel import worldref
from eglk_harness.domain.kernel.leaf_contract import assemble_leaf_contract
from eglk_harness.domain.kernel.compile_goal import load_goal_constraints, load_goal_excerpts
from eglk_harness.domain.kernel.projections import effective_cognitive_tokens_max, effective_repairs_max
from eglk_harness.domain.kernel.repair_counts import load_runtime_state, repair_counts_from_decisions
from eglk_harness.domain.kernel.swarm import SwarmPlan, decide_refiner, decide_swarm, should_veto_after_admit
from eglk_harness.domain.memory.tokens import add_tokens
from eglk_harness.domain.kernel.tree import TaskTree, make_root
from eglk_harness.protocol import topics

def _unwrap_stage_body(body: OkBody | ErrBody | Any) -> tuple[Any | None, str | None]:
    """Unwrap eba ResultBody to stage payload dict."""
    if is_result_ok(body):
        return result_value(body), None
    if is_result_err(body):
        return None, str(result_error(body))
    return body, None

def _stage_err(body: Any) -> str | None:
    """Legacy guard if inner payload still carries ``ok: false``."""
    if not isinstance(body, dict):
        return "non_dict_result"
    if body.get("ok") is False:
        return str(body.get("error") or "stage_failed")
    return None

class TickJob(Job):
    """One tick = Phase 0→1→2→3. Gate never reads candidates/ or refined Σ."""

    def __init__(
        self,
        *,
        workdir: Path,
        goal_id: str,
        tick: int = 0,
        goal_title: str = "goal",
        done_criteria: list[str] | None = None,
        swarm_soft: str | None = None,
        focus_score: float = 1.0,
        uncertainty: float = 0.0,
        quota: dict[str, Any] | None = None,
        maker_timeout_s: float | None = None,
        checker_timeout_s: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.workdir = Path(workdir).resolve()
        self.goal_id = goal_id
        self.tick = int(tick)
        self.goal_title = goal_title
        self.done_criteria = list(done_criteria or ["hello.txt exists"])
        self.swarm_soft = swarm_soft
        self.focus_score = float(focus_score)
        self.uncertainty = float(uncertainty)
        self.maker_timeout_s = maker_timeout_s
        self.checker_timeout_s = checker_timeout_s
        self.quota = dict(
            quota
            or {
                "cognitive_tokens": 0,
                "cognitive_tokens_max": effective_cognitive_tokens_max(),
                "repairs_max": effective_repairs_max(),
            }
        )
        if "cognitive_tokens_max" not in self.quota:
            self.quota["cognitive_tokens_max"] = effective_cognitive_tokens_max()
        if "repairs_max" not in self.quota:
            self.quota["repairs_max"] = effective_repairs_max()
        self.loop_dir: Path | None = None
        self.tree: TaskTree | None = None
        self.world: worldref.WorldRef | None = None
        self.claim: dict[str, Any] | None = None
        self.evidence: dict[str, Any] | None = None
        self.decision: dict[str, Any] | None = None
        self.written: list[str] = []
        self.outcome: dict[str, Any] | None = None
        self.swarm_plan: SwarmPlan | None = None
        self.phase0_queue: list[str] = []
        self.leaf_contract: dict[str, Any] | None = None
        self.phase3_record: dict[str, Any] | None = None
        self.gate_payload_keys: tuple[str, ...] | None = None
        self._pre_checker_fp: integrity.WorldFingerprint | None = None
        self.integrity_mutations: list[str] = []

    def _hydrate_runtime_from_state(self) -> None:
        """Resume quota / focus / uncertainty from prior tick state.json when unset."""
        assert self.loop_dir is not None
        st = load_runtime_state(self.loop_dir)
        if not st:
            return
        q = st.get("quota") if isinstance(st.get("quota"), dict) else {}
        if int(self.quota.get("cognitive_tokens") or 0) == 0 and q:
            self.quota["cognitive_tokens"] = int(q.get("cognitive_tokens") or 0)
            if q.get("cognitive_tokens_max") is not None:
                self.quota["cognitive_tokens_max"] = int(q["cognitive_tokens_max"])
            if q.get("usd_used") is not None:
                self.quota["usd_used"] = float(q["usd_used"])
        if "focus_score" in st:
            self.focus_score = float(st["focus_score"])
        if "uncertainty" in st:
            self.uncertainty = float(st["uncertainty"])

    def _apply_pending_merge_suggestions(self) -> None:
        """Apply Refiner Σ-similarity merge suggestions from prior tick (candidates/)."""
        assert self.loop_dir is not None and self.tree is not None
        cand = self.loop_dir / "candidates"
        if not cand.is_dir():
            return
        log = self.loop_dir / "reasoning_log.jsonl"
        any_applied = False
        for path in sorted(cand.glob("merge_suggest_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                path.unlink(missing_ok=True)
                continue
            parent_id = str(data.get("parent_id") or "")
            nodes = [str(x) for x in (data.get("nodes") or []) if str(x)]
            new_id = str(data.get("into") or f"{parent_id}.m{self.tick:03d}")
            title = str(data.get("title") or new_id)
            criteria = [str(x) for x in (data.get("done_criteria") or []) if str(x).strip()]
            applied = False
            if parent_id and len(nodes) >= 2 and criteria:
                try:
                    if self.tree.find(new_id) is None:
                        self.tree.merge_sibling_leaves(
                            parent_id=parent_id,
                            source_ids=nodes,
                            new_id=new_id,
                            title=title,
                            done_criteria=criteria,
                        )
                        self.tree.ensure_pointer()
                        applied = True
                        any_applied = True
                except (KeyError, ValueError):
                    applied = False
            with log.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "tick": self.tick,
                            "event": "merge_suggest_apply",
                            "applied": applied,
                            "suggestion": data,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            path.unlink(missing_ok=True)
        if any_applied:
            loop_store.save_tree(self.loop_dir, self.tree)

    async def begin(self) -> None:
        self.loop_dir = loop_store.ensure_loop_layout(self.workdir, self.goal_id)
        self._hydrate_runtime_from_state()
        tree = loop_store.load_tree(self.loop_dir)
        if tree is None:
            tree = make_root(self.goal_title, self.done_criteria, leaf=True)
        tree.ensure_pointer()
        loop_store.save_tree(self.loop_dir, tree)
        self.tree = tree
        self._apply_pending_merge_suggestions()

        snap = loop_store.world_pre_dir(self.loop_dir, self.tick)
        self.world = worldref.snapshot_workdir(
            self.workdir,
            snap,
            revision=self.tick,
            tick=self.tick,
            meta={"goal_id": self.goal_id},
        )

        cand_count = len(list((self.loop_dir / "candidates").glob("*.json")))
        self.swarm_plan = decide_swarm(
            focus_score=self.focus_score,
            uncertainty=self.uncertainty,
            candidate_count=cand_count,
            cognitive_tokens=int(self.quota.get("cognitive_tokens", 0) or 0),
            cognitive_tokens_max=int(self.quota.get("cognitive_tokens_max", 64000) or 64000),
            soft=self.swarm_soft,
        )

        # Governor when split streak requires it (not decide_swarm)
        if tree.should_split():
            cur = tree.in_progress() or tree.find_pending_with_streak()
            await self.request(
                stage="governor",
                request_prefix=topics.ROLE_GOVERNOR_RUN,
                result_prefix=topics.ROLE_GOVERNOR_RESULT,
                payload={
                    "args": {
                        "tick": self.tick,
                        "loop_dir": str(self.loop_dir),
                        "subgoal_id": cur.id if cur else "root",
                        "goal_title": cur.title if cur else self.goal_title,
                        "done_criteria": list(cur.done_criteria) if cur else list(self.done_criteria),
                        "repair_streak": int(cur.repair_streak) if cur else 0,
                        "workdir": str(self.workdir),
                    }
                },
            )
            return

        await self._start_phase0()

    async def _start_phase0(self) -> None:
        assert self.swarm_plan is not None
        q: list[str] = []
        if self.swarm_plan.explorer:
            q.append("explorer")
        if self.swarm_plan.verifier:
            q.append("verifier")
        if self.swarm_plan.pruner:
            q.append("pruner")
        self.phase0_queue = q
        if not q:
            await self._start_phase1()
            return
        await self._request_next_phase0()

    async def _request_next_phase0(self) -> None:
        assert self.loop_dir is not None and self.tree is not None
        if not self.phase0_queue:
            await self._start_phase1()
            return
        role = self.phase0_queue.pop(0)
        cur = self.tree.in_progress()
        prefixes = {
            "explorer": (topics.ROLE_EXPLORER_RUN, topics.ROLE_EXPLORER_RESULT),
            "verifier": (topics.ROLE_VERIFIER_RUN, topics.ROLE_VERIFIER_RESULT),
            "pruner": (topics.ROLE_PRUNER_RUN, topics.ROLE_PRUNER_RESULT),
        }
        req, res = prefixes[role]
        lc_payload = self.leaf_contract if isinstance(self.leaf_contract, dict) else None
        if lc_payload is None and self.tree is not None:
            cur_pre = self.tree.in_progress()
            if cur_pre is not None:
                try:
                    gmd, gfmt = load_goal_excerpts(self.workdir)
                    pre = assemble_leaf_contract(
                        cur_pre,
                        tick=self.tick,
                        goal_constraints=load_goal_constraints(self.workdir),
                        goal_md_excerpt=gmd,
                        goal_format_excerpt=gfmt,
                        root_acceptance=list(self.tree.root.done_criteria)
                        if self.tree.root
                        else [],
                    )
                    lc_payload = pre.to_dict()
                except ValueError:
                    lc_payload = None
        await self.request(
            stage=f"phase0_{role}",
            request_prefix=req,
            result_prefix=res,
            payload={
                "args": {
                    "tick": self.tick,
                    "loop_dir": str(self.loop_dir),
                    "subgoal_id": cur.id if cur else "root",
                    "goal_title": cur.title if cur else self.goal_title,
                    "done_criteria": list(cur.done_criteria) if cur else list(self.done_criteria),
                    "workdir": str(self.workdir),
                    "leaf_contract": lc_payload,
                }
            },
        )

    def _load_phase0_priors(self) -> list[dict[str, Any]]:
        assert self.loop_dir is not None
        priors: list[dict[str, Any]] = []
        cand = self.loop_dir / "candidates"
        for name in (f"explorer_{self.tick:03d}.json", f"verifier_{self.tick:03d}.json", f"pruner_{self.tick:03d}.json"):
            path = cand / name
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if name.startswith("explorer"):
                for a in data.get("alternatives") or []:
                    if isinstance(a, dict) and not a.get("pruned"):
                        priors.append({"kind": "alternative", "text": str(a.get("text", "")), "ref": a.get("id")})
            if name.startswith("verifier"):
                for c in data.get("challenges") or []:
                    if isinstance(c, dict):
                        priors.append({"kind": "challenge", "text": str(c.get("title") or c.get("text", "")), "ref": c.get("id")})
        return priors

    async def _start_phase1(self) -> None:
        assert self.loop_dir is not None and self.tree is not None
        cur = self.tree.ensure_pointer()
        if cur is None:
            # Spurious extra tick after last admit (or empty tree): succeed cleanly.
            if self.tree.all_work_admitted():
                self.decision = {
                    "decision": "admit",
                    "reason": "already_complete",
                    "should_run_next": False,
                    "next_action": "advance",
                    "tick": self.tick,
                }
                await self.finish(
                    ok=True,
                    answer={
                        "decision": self.decision,
                        "root_done": True,
                        "written": [],
                        "note": "no_in_progress_leaf_but_all_admitted",
                    },
                )
                return
            await self.finish(ok=False, error="no_in_progress_leaf")
            return
        lessons = [x for x in sigma.load_active(self.workdir) if x.get("kind") == "lesson"][-5:]
        hints = skill_lib.boundary_hints(self.workdir, leaf_id=cur.id, title=cur.title)
        matched = skill_lib.match_skills(
            self.workdir,
            leaf_id=cur.id,
            title=cur.title,
            acceptance=list(cur.done_criteria),
        )
        learned = skill_lib.render_learned_skills_block(matched)
        goal_cons = load_goal_constraints(self.workdir)
        goal_md, goal_fmt = load_goal_excerpts(self.workdir)
        root_acc = list(self.tree.root.done_criteria) if self.tree.root else []
        from eglk_harness.domain.kernel.repair_feedback import load_prior_repair_feedback

        repair_fb = load_prior_repair_feedback(self.loop_dir, current_tick=self.tick)
        try:
            contract = assemble_leaf_contract(
                cur,
                tick=self.tick,
                goal_constraints=goal_cons,
                prior_evidence=self._load_phase0_priors(),
                sigma_lessons=lessons,
                skill_hints=hints,
                learned_skills_block=learned,
                goal_md_excerpt=goal_md,
                goal_format_excerpt=goal_fmt,
                root_acceptance=root_acc,
                repair_feedback=repair_fb,
            )
        except ValueError as exc:
            await self.finish(ok=False, error=f"leaf_contract:{exc}")
            return
        self.leaf_contract = contract.to_dict()
        # Store for Phase 3 archive — not Gate input
        (self.loop_dir / "candidates").mkdir(parents=True, exist_ok=True)
        (self.loop_dir / "candidates" / f"leaf_contract_{self.tick:03d}.json").write_text(
            json.dumps(self.leaf_contract, indent=2) + "\n",
            encoding="utf-8",
        )

        await self.request(
            stage="maker",
            request_prefix=topics.ROLE_MAKER_RUN,
            result_prefix=topics.ROLE_MAKER_RESULT,
            payload={
                "args": {
                    "tick": self.tick,
                    "subgoal_id": cur.id,
                    "done_criteria": list(cur.done_criteria),
                    "goal_id": self.goal_id,
                    "goal_title": cur.title,
                    "leaf_contract": self.leaf_contract,
                    "workdir": str(self.workdir),
                    "timeout_s": self.maker_timeout_s or 600.0,
                    "tee_path": str(
                        self.loop_dir / "agent_logs" / f"maker_{self.tick:03d}.jsonl"
                    ),
                }
            },
        )

    async def on_stage_result(self, stage: str, body: OkBody | ErrBody) -> None:
        inner, transport_err = _unwrap_stage_body(body)
        if transport_err is not None:
            await self.finish(ok=False, error=transport_err)
            return
        body = inner
        err = _stage_err(body)
        if err is not None:
            await self.finish(ok=False, error=err)
            return

        assert isinstance(body, dict)
        assert self.loop_dir is not None and self.tree is not None

        if stage == "governor":
            proposal = body.get("proposal") if isinstance(body.get("proposal"), dict) else {}
            node_id = str(proposal.get("split_node") or "")
            children = proposal.get("children") or []
            if node_id and isinstance(children, list) and children:
                try:
                    self.tree.split_node(node_id, children)
                    loop_store.save_tree(self.loop_dir, self.tree)
                except (KeyError, ValueError) as exc:
                    await self.finish(ok=False, error=f"split_failed:{exc}")
                    return
            await self._start_phase0()
            return

        if stage.startswith("phase0_"):
            await self._request_next_phase0()
            return

        if stage == "maker":
            claim = body.get("claim")
            if not isinstance(claim, dict):
                await self.finish(ok=False, error="maker_missing_claim")
                return
            self.claim = claim
            self.quota = add_tokens(self.quota, int(body.get("tokens") or 0))
            self.quota["usd_used"] = float(self.quota.get("usd_used") or 0) + float(
                body.get("cost_usd") or 0
            )
            try:
                written: list[str] = []
                written.extend(
                    worldref.apply_claim_actions(
                        self.workdir,
                        claim.get("actions") if isinstance(claim.get("actions"), list) else None,
                    )
                )
                payload = claim.get("payload") if isinstance(claim.get("payload"), dict) else None
                written.extend(worldref.apply_claim_payload(self.workdir, payload))
                self.written = list(dict.fromkeys(written))
            except ValueError as exc:
                await self.finish(ok=False, error=f"apply_failed:{exc}")
                return
            from eglk_harness.domain.runtime.evidence_guard import align_claim_delivery_progress

            boundary = (
                list(self.leaf_contract.get("boundary") or [])
                if isinstance(self.leaf_contract, dict)
                else []
            )
            claim = align_claim_delivery_progress(
                claim,
                workdir=self.workdir,
                boundary=boundary or None,
            )
            self.claim = claim
            loop_store.write_claim(self.loop_dir, self.tick, claim)

            cur = self.tree.in_progress()
            self._pre_checker_fp = integrity.fingerprint_workdir(self.workdir)
            await self.request(
                stage="checker",
                request_prefix=topics.ROLE_CHECKER_RUN,
                result_prefix=topics.ROLE_CHECKER_RESULT,
                payload={
                    "args": {
                        "tick": self.tick,
                        "subgoal_id": cur.id if cur else "root",
                        "claim": claim,
                        "written": list(self.written),
                        "goal_id": self.goal_id,
                        "goal_title": cur.title if cur else self.goal_title,
                        "done_criteria": list(cur.done_criteria) if cur else list(self.done_criteria),
                        "leaf_contract": self.leaf_contract,
                        "workdir": str(self.workdir),
                        "timeout_s": self.checker_timeout_s or 600.0,
                        "tee_path": str(
                            self.loop_dir / "agent_logs" / f"checker_{self.tick:03d}.jsonl"
                        ),
                    }
                },
            )
            return

        if stage == "checker":
            evidence = body.get("evidence")
            if not isinstance(evidence, dict):
                await self.finish(ok=False, error="checker_missing_evidence")
                return
            self.quota = add_tokens(self.quota, int(body.get("tokens") or 0))
            self.quota["usd_used"] = float(self.quota.get("usd_used") or 0) + float(
                body.get("cost_usd") or 0
            )
            # Invariant #11: Checker must not mutate the task world
            if self._pre_checker_fp is not None:
                after_fp = integrity.fingerprint_workdir(self.workdir)
                self.integrity_mutations = integrity.apply_integrity_flag(
                    evidence, before=self._pre_checker_fp, after=after_fp
                )
            self.evidence = evidence
            loop_store.write_evidence(self.loop_dir, self.tick, evidence)
            cur = self.tree.in_progress()
            leaf_id = cur.id if cur else None
            # Gate inputs: Claim + Evidence + quota + repair_counts (truth-blind; no candidates/Σ)
            gate_args = {
                "claim": self.claim,
                "evidence": evidence,
                "quota": dict(self.quota),
                "repair_counts": repair_counts_from_decisions(self.loop_dir, subgoal_id=leaf_id),
            }
            self.gate_payload_keys = tuple(sorted(gate_args.keys()))
            await self.request(
                stage="gate",
                request_prefix=topics.GATE_DECIDE,
                result_prefix=topics.GATE_RESULT,
                payload={"args": gate_args},
            )
            return

        if stage == "gate":
            decision = body.get("decision")
            if not isinstance(decision, dict):
                await self.finish(ok=False, error="gate_missing_decision")
                return
            cur = self.tree.in_progress()
            decision = dict(decision)
            if cur is not None and "subgoal_id" not in decision:
                decision["subgoal_id"] = cur.id
            self.decision = decision
            loop_store.write_decision(self.loop_dir, self.tick, decision)
            await self._apply_gate_tree(decision)
            await self._start_phase2(decision)
            return

        if stage == "refiner":
            # refined written by actor; must NOT merge yet (same-tick Gate already done)
            if (
                self.decision
                and self.decision.get("decision") == "admit"
                and should_veto_after_admit(self.evidence)
            ):
                leaf_id = str(self.decision.get("subgoal_id") or "root")
                cur = self.tree.find(leaf_id) or self.tree.root
                await self.request(
                    stage="veto",
                    request_prefix=topics.ROLE_VERIFIER_RUN,
                    result_prefix=topics.ROLE_VERIFIER_RESULT,
                    payload={
                        "args": {
                            "tick": self.tick,
                            "loop_dir": str(self.loop_dir),
                            "subgoal_id": leaf_id,
                            "goal_title": cur.title,
                            "done_criteria": list(cur.done_criteria),
                            "veto_audit": True,
                        }
                    },
                )
                return
            await self._finish_phase3()
            return

        if stage == "veto":
            await self._finish_phase3()
            return

        await self.finish(ok=False, error=f"unknown_stage:{stage}")

    async def _apply_gate_tree(self, decision: dict[str, Any]) -> None:
        assert self.loop_dir is not None and self.tree is not None
        kind = str(decision.get("decision") or "")
        if kind == "admit":
            cur = self.tree.in_progress()
            self.tree.admit_current()
            merge_event = None
            if cur is not None:
                merge_event = self.tree.try_merge_siblings_after_admit(cur.id)
            loop_store.save_tree(self.loop_dir, self.tree)
            if merge_event is not None:
                log = self.loop_dir / "reasoning_log.jsonl"
                with log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"tick": self.tick, **merge_event}, ensure_ascii=False) + "\n")
            if cur is not None:
                skill_lib.record_admit(
                    self.workdir,
                    leaf_id=cur.id,
                    title=cur.title,
                    tick=self.tick,
                    claim=self.claim,
                )
            return
        if kind == "repair":
            if self.world is not None:
                self.world = worldref.restore(self.world, self.workdir)
            self.tree.repair_current()
            self.tree.ensure_pointer()
            loop_store.save_tree(self.loop_dir, self.tree)
            return
        self.tree.fail_current()
        loop_store.save_tree(self.loop_dir, self.tree)

    async def _start_phase2(self, decision: dict[str, Any]) -> None:
        assert self.loop_dir is not None
        kind = str(decision.get("decision") or "")
        staging_count = len(sigma.list_refined(self.loop_dir))
        leaf_id = str(decision.get("subgoal_id") or "root")
        cur = self.tree.find(leaf_id) if self.tree else None
        if decide_refiner(sigma_staging_count=staging_count, decision=kind):
            await self.request(
                stage="refiner",
                request_prefix=topics.ROLE_REFINER_RUN,
                result_prefix=topics.ROLE_REFINER_RESULT,
                payload={
                    "args": {
                        "tick": self.tick,
                        "loop_dir": str(self.loop_dir),
                        "decision": kind,
                        "reason": str(decision.get("reason") or ""),
                        "subgoal_id": leaf_id,
                        "claim": self.claim,
                        "evidence": self.evidence,
                        "workdir": str(self.workdir),
                    }
                },
            )
            return
        # Skip refiner; maybe still veto
        if kind == "admit" and should_veto_after_admit(self.evidence):
            await self.request(
                stage="veto",
                request_prefix=topics.ROLE_VERIFIER_RUN,
                result_prefix=topics.ROLE_VERIFIER_RESULT,
                payload={
                    "args": {
                        "tick": self.tick,
                        "loop_dir": str(self.loop_dir),
                        "subgoal_id": leaf_id,
                        "goal_title": cur.title if cur else self.goal_title,
                        "done_criteria": list(cur.done_criteria) if cur else list(self.done_criteria),
                        "veto_audit": True,
                    }
                },
            )
            return
        await self._finish_phase3()

    async def _finish_phase3(self) -> None:
        assert self.loop_dir is not None and self.decision is not None
        # Prove refined still staged before merge
        refined_before = sigma.list_refined(self.loop_dir)
        self.phase3_record = phase3.run_phase3(
            self.workdir,
            self.loop_dir,
            tick=self.tick,
            decision=self.decision,
            swarm_enabled=self.swarm_plan,
            written=self.written,
            quota=self.quota,
            focus_score=self.focus_score,
            uncertainty=self.uncertainty,
            soft=self.swarm_soft,
        )
        # Persist updated scores for next tick hydration
        if self.phase3_record:
            self.focus_score = float(self.phase3_record.get("focus_score", self.focus_score))
            self.uncertainty = float(self.phase3_record.get("uncertainty", self.uncertainty))
        kind = str(self.decision.get("decision") or "")
        done = bool(self.tree and self.tree.all_work_admitted()) if kind == "admit" else False
        answer = {
            "decision": self.decision,
            "root_done": done,
            "written": list(self.written),
            "swarm_enabled": self.swarm_plan.to_dict() if self.swarm_plan else {},
            "phase3": self.phase3_record,
            "gate_payload_keys": list(self.gate_payload_keys or ()),
            "refined_staged_before_phase3": len(refined_before),
            "quota": dict(self.quota),
            "focus_score": self.focus_score,
            "uncertainty": self.uncertainty,
        }
        if kind == "abort":
            await self.finish(ok=False, error=str(self.decision.get("reason") or "abort"), answer=answer)
            return
        if kind == "repair":
            answer["rolled_back"] = True
        await self.finish(ok=True, answer=answer)

    async def finish(
        self, *, ok: bool, error: str | None = None, answer: Any = None
    ) -> None:
        # Publish outcome *before* ``finished`` flips so the run loop's
        # ``_should_continue`` cannot race and miss ``root_done``.
        self.outcome = {"ok": ok, "error": error, "answer": answer}
        await super().finish(ok=ok, error=error, answer=answer)

    async def on_finished(
        self, *, ok: bool, error: str | None = None, answer: Any = None
    ) -> None:
        self.outcome = {"ok": ok, "error": error, "answer": answer}
