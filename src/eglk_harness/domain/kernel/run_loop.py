"""Tick orchestration — Phase 0→3; Gate via CommandHandler only (kernel SSOT)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eba import ErrBody, OkBody, is_result_err, is_result_ok, result_error, result_value

from eglk_harness.domain.kernel import integrity
from eglk_harness.domain.kernel import loop_store
from eglk_harness.domain.memory import phase3
from eglk_harness.domain.memory import sigma
from eglk_harness.domain.memory import skill_lib
from eglk_harness.domain.kernel import worldref
from eglk_harness.domain.kernel.leaf_contract import assemble_leaf_contract
from eglk_harness.domain.kernel.compile_goal import load_goal_constraints, load_goal_excerpts
from eglk_harness.domain.kernel.projections import effective_cognitive_tokens_max, effective_repairs_max
from eglk_harness.domain.kernel.repair_counts import repair_counts_from_decisions
from eglk_harness.domain.kernel.event_runtime import RunEventContext
from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.advisors import build_mechanical_split_candidate
from eglk_harness.domain.kernel.scheduler import should_propose_split
from eglk_harness.domain.kernel.swarm import SwarmPlan, decide_swarm, should_veto_after_admit
from eglk_harness.domain.memory.tokens import add_tokens
from eglk_harness.domain.kernel.tree import TaskTree
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

class TickRunLoop:
    """One tick = Phase 0→1→2→3. Mixed into ``TickJob`` (EBA Job adapter)."""

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
    ) -> None:
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
        self.ctx: RunEventContext | None = None
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
        """Resume quota / focus from run_projection (SSOT) and ticks.jsonl."""
        assert self.loop_dir is not None
        from eglk_harness.domain.kernel.projection_read import hydrate_runtime_signals

        self.quota, focus, uncertainty = hydrate_runtime_signals(
            self.quota, self.loop_dir, self.workdir, self.goal_id
        )
        if focus is not None:
            self.focus_score = focus
        if uncertainty is not None:
            self.uncertainty = uncertainty

    def _apply_pending_merge_suggestions(self) -> None:
        """Apply Refiner merge suggestions via CommandHandler.commit_merge."""
        assert self.loop_dir is not None
        if self.ctx is None:
            return
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
            if not parent_id or len(nodes) < 1:
                path.unlink(missing_ok=True)
                continue
            proj = self.ctx.projection()
            merged_refs: list[str] = []
            for nid in nodes:
                node = proj.nodes.get(nid)
                if node is not None:
                    merged_refs.extend(node.obligation_refs)
            merged_refs = list(dict.fromkeys(merged_refs))
            res = self.ctx.handler.commit_merge(
                {
                    "into": new_id,
                    "node_ids": nodes,
                    "parent_id": parent_id,
                    "title": str(data.get("title") or new_id),
                    "obligation_refs": merged_refs,
                },
                actor="refiner",
            )
            applied = res.ok
            if applied:
                any_applied = True
            with log.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "tick": self.tick,
                            "event": "merge_suggest_apply",
                            "applied": applied,
                            "via": "commit_merge",
                            "suggestion": data,
                            "error": res.error,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            path.unlink(missing_ok=True)
        if any_applied:
            self.ctx.export_projections(tick=self.tick)
            self.tree = self.ctx.sync_tree()

    async def begin(self) -> None:
        self.loop_dir = loop_store.ensure_loop_layout(self.workdir, self.goal_id)
        self._hydrate_runtime_from_state()
        self.ctx = RunEventContext(self.workdir, self.goal_id)
        self.ctx.acquire()
        self.ctx.bootstrap_if_needed(goal_title=self.goal_title, done_criteria=self.done_criteria)
        self._apply_pending_merge_suggestions()
        self.tree = self.ctx.sync_tree()

        proj = self.ctx.projection()
        node_id = self.ctx.select_node_id()
        if node_id and should_propose_split(proj, node_id, P.SPLIT_REPAIR_STREAK):
            cur = self.tree.in_progress() or self.tree.find(node_id)
            await self.request(
                stage="governor",
                request_prefix=topics.ROLE_GOVERNOR_RUN,
                result_prefix=topics.ROLE_GOVERNOR_RESULT,
                payload={
                    "args": {
                        "tick": self.tick,
                        "loop_dir": str(self.loop_dir),
                        "subgoal_id": cur.id if cur else node_id,
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
        assert self.loop_dir is not None
        snap = loop_store.world_pre_dir(self.loop_dir, self.tick)
        self.world = worldref.snapshot_workdir(
            self.workdir,
            snap,
            revision=self.tick,
            tick=self.tick,
            meta={"goal_id": self.goal_id},
        )

        cand_count = len(list((self.loop_dir / "candidates").glob("*.json")))
        from eglk_harness.domain.kernel.projection_read import read_last_tick_record

        last_rec = read_last_tick_record(self.loop_dir)
        last_repair_reason: str | None = None
        if isinstance(last_rec, dict) and str(last_rec.get("decision") or "") == "repair":
            last_repair_reason = str(last_rec.get("reason") or "") or None
        self.swarm_plan = decide_swarm(
            focus_score=self.focus_score,
            uncertainty=self.uncertainty,
            candidate_count=cand_count,
            cognitive_tokens=int(self.quota.get("cognitive_tokens", 0) or 0),
            cognitive_tokens_max=int(self.quota.get("cognitive_tokens_max", 64000) or 64000),
            soft=self.swarm_soft,
            last_repair_reason=last_repair_reason,
        )
        assert self.swarm_plan is not None
        q: list[str] = []
        if self.swarm_plan.explorer:
            q.append("explorer")
        if self.swarm_plan.verifier:
            q.append("verifier")
        if self.swarm_plan.pruner:
            q.append("candidate_selector")
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
            "candidate_selector": (topics.ROLE_PRUNER_RUN, topics.ROLE_PRUNER_RESULT),
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
        for name in (
            f"explorer_{self.tick:03d}.json",
            f"verifier_{self.tick:03d}.json",
            f"candidate_selector_{self.tick:03d}.json",
            f"pruner_{self.tick:03d}.json",
        ):
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
        assert self.loop_dir is not None and self.tree is not None and self.ctx is not None
        if self.ctx.closure_needed():
            closure = self.ctx.run_closure_gate()
            self.ctx.export_projections(tick=self.tick)
            if self.ctx.handler.projection().run_status == "succeeded":
                self.decision = dict(
                    (closure.events[0].payload if closure.events else {})
                    or {"decision": "admit", "reason": "closure_admitted"}
                )
                await self._finish_phase3()
                return
            await self.finish(ok=False, error="closure_gate_failed")
            return
        if self.ctx.handler.projection().run_status == "succeeded":
            self.decision = {
                "decision": "admit",
                "reason": "already_succeeded",
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
                    "run_status": "succeeded",
                    "note": "already_succeeded",
                },
            )
            return
        node_id = self.ctx.select_node_id()
        if node_id is None:
            if self.ctx.closure_needed():
                closure = self.ctx.run_closure_gate()
                self.ctx.export_projections()
                if self.ctx.handler.projection().run_status == "succeeded":
                    self.decision = dict(
                        (closure.events[0].payload if closure.events else {})
                        or {"decision": "admit", "reason": "closure_admitted"}
                    )
                    await self.finish(
                        ok=True,
                        answer={
                            "decision": self.decision,
                            "root_done": True,
                            "written": [],
                            "note": "closure_gate_succeeded",
                        },
                    )
                    return
            await self.finish(ok=False, error="no_ready_node")
            return
        cur = self.tree.find(node_id) or self.tree.in_progress()
        if cur is None:
            self.tree = self.ctx.sync_tree()
            cur = self.tree.find(node_id)
        if cur is None:
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
        contract_doc = self.ctx.assemble_contract_for_node(
            node_id,
            repair_feedback=repair_fb,
            prior_evidence_refs=[str(x.get("ref") or "") for x in self._load_phase0_priors() if isinstance(x, dict)],
        )
        self.ctx.contract_assembled(contract_doc)
        contract_ref = str(contract_doc.get("contract_id") or "")
        obligation_refs = list(contract_doc.get("obligation_refs") or [])
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
                    "obligation_refs": obligation_refs,
                    "contract_ref": contract_ref,
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

        if stage.startswith("phase0_"):
            role = stage.replace("phase0_", "")
            if self.ctx is not None:
                self.ctx.quota(
                    role,
                    int(body.get("tokens") or 1),
                    float(body.get("cost_usd") or 0),
                )
            await self._request_next_phase0()
            return

        if stage == "governor":
            assert self.ctx is not None
            self.ctx.quota(
                "governor",
                int(body.get("tokens") or 1),
                float(body.get("cost_usd") or 0),
            )
            proposal = body.get("proposal") if isinstance(body.get("proposal"), dict) else {}
            node_id = str(proposal.get("split_node") or "")
            mechanical = build_mechanical_split_candidate(
                self.ctx.projection(), node_id, step=self.tick
            )
            if mechanical is None and node_id:
                mechanical = {
                    "split_node": node_id,
                    "children": proposal.get("children") or [],
                    "coverage_proof": proposal.get("coverage_proof") or {},
                    "opened_obligations": proposal.get("opened_obligations") or [],
                }
            if mechanical:
                res = self.ctx.handler.commit_split(mechanical, actor="governor")
                if not res.ok:
                    await self.finish(ok=False, error=f"split_failed:{res.error}")
                    return
                self.tree = self.ctx.sync_tree()
            await self._start_phase0()
            return

        if stage == "maker":
            assert self.ctx is not None
            claim = body.get("claim")
            if not isinstance(claim, dict):
                await self.finish(ok=False, error="maker_missing_claim")
                return
            self.claim = claim
            fr_tokens = int(body.get("format_repair_tokens") or 0)
            fr_cost = float(body.get("format_repair_cost_usd") or 0.0)
            total_tokens = int(body.get("tokens") or 0)
            primary_tokens = max(1, total_tokens - fr_tokens) if fr_tokens else max(1, total_tokens)
            self.quota = add_tokens(self.quota, total_tokens)
            self.quota["usd_used"] = float(self.quota.get("usd_used") or 0) + float(
                body.get("cost_usd") or 0
            )
            self.ctx.quota("maker", primary_tokens, float(body.get("cost_usd") or 0) - fr_cost)
            if fr_tokens > 0:
                self.ctx.quota("format_repair", fr_tokens, fr_cost)
            try:
                from eglk_harness.domain.kernel.worldref import resolve_claim_payload

                payload = resolve_claim_payload(claim)
                tx = self.ctx.apply_claim_to_tx(claim, payload=payload)
                self.written = list(tx.touches)
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
            cur = self.tree.in_progress()
            if cur is None and self.ctx is not None:
                nid = self.ctx.select_node_id()
                if nid:
                    cur = self.tree.find(nid)
            self._pre_checker_fp = integrity.fingerprint_workdir(self.workdir)
            active_contract = self.ctx._active_contract or {}
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
                        "obligation_refs": list(active_contract.get("obligation_refs") or []),
                        "contract_ref": str(active_contract.get("contract_id") or ""),
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
            assert self.ctx is not None
            evidence = body.get("evidence")
            if not isinstance(evidence, dict):
                await self.finish(ok=False, error="checker_missing_evidence")
                return
            self.quota = add_tokens(self.quota, int(body.get("tokens") or 0))
            self.quota["usd_used"] = float(self.quota.get("usd_used") or 0) + float(
                body.get("cost_usd") or 0
            )
            fr_tokens = int(body.get("format_repair_tokens") or 0)
            fr_cost = float(body.get("format_repair_cost_usd") or 0.0)
            total_tokens = int(body.get("tokens") or 0)
            primary_tokens = max(1, total_tokens - fr_tokens) if fr_tokens else max(1, total_tokens)
            self.ctx.quota("checker", primary_tokens, float(body.get("cost_usd") or 0) - fr_cost)
            if fr_tokens > 0:
                self.ctx.quota("format_repair", fr_tokens, fr_cost)
            if self._pre_checker_fp is not None:
                after_fp = integrity.fingerprint_workdir(self.workdir)
                self.integrity_mutations = integrity.apply_integrity_flag(
                    evidence, before=self._pre_checker_fp, after=after_fp
                )
            cur = self.tree.in_progress()
            leaf_id = cur.id if cur else None
            claim = self.claim or {}
            contract = self.ctx._active_contract or {}
            if not contract:
                node_id = leaf_id or self.ctx.select_node_id() or "root"
                contract = self.ctx.assemble_contract_for_node(node_id)
                self.ctx.contract_assembled(contract)
            claim = dict(claim)
            claim.setdefault("contract_ref", contract.get("contract_id"))
            claim.setdefault("node_id", contract.get("node_id") or leaf_id)
            self.ctx.dispatch_claim(claim, actor=str(claim.get("maker_session_id") or "maker"))
            evidence = dict(evidence)
            tx = self.ctx._active_tx
            if tx is not None:
                from eglk_harness.domain.runtime.evidence_guard import align_evidence_world_revision

                evidence = align_evidence_world_revision(
                    evidence,
                    self.ctx.env.observe_revision(tx),
                )
            contract_obligations = list(contract.get("obligation_refs") or [])
            from eglk_harness.domain.runtime.contract_align import align_evidence_to_contract
            from eglk_harness.domain.kernel.schema_validate import coerce_document

            evidence = align_evidence_to_contract(
                evidence,
                contract_ref=str(contract.get("contract_id") or ""),
                obligation_refs=contract_obligations,
                world_revision=int(evidence.get("world_revision") or 0),
            )
            evidence = coerce_document("evidence", evidence)
            claim = coerce_document("action_claim", claim)
            self.evidence = evidence
            rec = self.ctx.record_evidence(evidence, actor=str(evidence.get("checker_session_id") or "checker"))
            if not rec.ok:
                await self.finish(ok=False, error=rec.error or "evidence_rejected")
                return
            self.ctx.handler.record_defect_suspected_amendments(evidence, actor="governor")
            self.gate_payload_keys = ("claim", "evidence", "events")
            gd = self.ctx.gate_decide(claim=claim, evidence=evidence)
            decision = gd.events[0].payload if gd.events else {}
            if cur is not None and "subgoal_id" not in decision:
                decision["subgoal_id"] = cur.id
            self.decision = dict(decision)
            self.ctx.finalize_transaction_after_gate(str(decision.get("decision") or ""))
            await self._apply_gate_projection()
            if self.ctx.closure_needed():
                closure = self.ctx.run_closure_gate()
                if closure.events:
                    self.decision = dict(closure.events[0].payload)
                if self.ctx.handler.projection().run_status == "succeeded":
                    self.tree = self.ctx.sync_tree()
                    self.ctx.export_projections(tick=self.tick)
                    await self._finish_phase3()
                    return
            self.tree = self.ctx.sync_tree()
            self.ctx.export_projections(tick=self.tick)
            await self._start_phase2(self.decision)
            return

        if stage == "veto":
            if self.ctx is not None:
                self.ctx.quota(
                    "verifier",
                    int(body.get("tokens") or 1),
                    float(body.get("cost_usd") or 0),
                )
            await self._finish_phase3()
            return

        await self.finish(ok=False, error=f"unknown_stage:{stage}")

    async def _apply_gate_projection(self) -> None:
        """Sync in-memory tree view from event projection after Gate."""
        assert self.loop_dir is not None and self.ctx is not None
        self.tree = self.ctx.sync_tree()
        if self.decision and self.decision.get("decision") == "admit":
            cur = self.tree.in_progress()
            if cur is not None:
                skill_lib.record_admit(
                    self.workdir,
                    leaf_id=cur.id,
                    title=cur.title,
                    tick=self.tick,
                    claim=self.claim,
                )

    async def _start_phase2(self, decision: dict[str, Any]) -> None:
        assert self.loop_dir is not None
        kind = str(decision.get("decision") or "")
        leaf_id = str(decision.get("subgoal_id") or "root")
        cur = self.tree.find(leaf_id) if self.tree else None
        # Refiner is run-end batch only (multi_agent §5.4) — never per-tick.
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
            handler=self.ctx.handler if self.ctx else None,
            claim=self.claim if isinstance(self.claim, dict) else None,
            evidence=self.evidence if isinstance(self.evidence, dict) else None,
        )
        # Persist updated scores for next tick hydration
        if self.phase3_record:
            self.focus_score = float(self.phase3_record.get("focus_score", self.focus_score))
            self.uncertainty = float(self.phase3_record.get("uncertainty", self.uncertainty))
        kind = str(self.decision.get("decision") or "")
        done = self.ctx.root_done() if self.ctx else bool(self.tree and self.tree.all_work_admitted())
        run_status = self.ctx.handler.projection().run_status if self.ctx else None
        answer = {
            "decision": self.decision,
            "root_done": done,
            "run_status": run_status,
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
        if self.ctx is not None:
            self.ctx.export_projections(tick=self.tick)
            self.ctx.release()
        await self.finish(ok=True, answer=answer)
