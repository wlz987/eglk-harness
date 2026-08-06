"""TickJob — four phases: Phase0 SWARM → Phase1 main → Phase2 refine/veto → Phase3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eba_job import Job

from eglk_harness.domain import integrity, loop_store, phase3, sigma, worldref
from eglk_harness.domain.leaf_contract import assemble_leaf_contract
from eglk_harness.domain.swarm import SwarmPlan, decide_refiner, decide_swarm, should_veto_after_admit
from eglk_harness.domain.tree import TaskTree, make_root
from eglk_harness.protocol import topics


def _stage_err(body: Any) -> str | None:
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
        self.quota = dict(quota or {"cognitive_tokens": 0})
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

    async def begin(self) -> None:
        self.loop_dir = loop_store.ensure_loop_layout(self.workdir, self.goal_id)
        tree = loop_store.load_tree(self.loop_dir)
        if tree is None:
            tree = make_root(self.goal_title, self.done_criteria, leaf=True)
        tree.ensure_pointer()
        loop_store.save_tree(self.loop_dir, tree)
        self.tree = tree

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
        await self.request(
            stage=f"phase0_{role}",
            request_prefix=req,
            result_prefix=res,
            payload={
                "args": {
                    "tick": self.tick,
                    "loop_dir": str(self.loop_dir),
                    "subgoal_id": cur.id if cur else "root",
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
            await self.finish(ok=False, error="no_in_progress_leaf")
            return
        try:
            contract = assemble_leaf_contract(
                cur,
                tick=self.tick,
                prior_evidence=self._load_phase0_priors(),
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
                }
            },
        )

    async def on_stage_result(self, stage: str, body: Any) -> None:
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
            loop_store.write_claim(self.loop_dir, self.tick, claim)
            try:
                self.written = worldref.apply_claim_payload(
                    self.workdir,
                    claim.get("payload") if isinstance(claim.get("payload"), dict) else None,
                )
            except ValueError as exc:
                await self.finish(ok=False, error=f"apply_failed:{exc}")
                return

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
                        "workdir": str(self.workdir),
                    }
                },
            )
            return

        if stage == "checker":
            evidence = body.get("evidence")
            if not isinstance(evidence, dict):
                await self.finish(ok=False, error="checker_missing_evidence")
                return
            # Invariant #11: Checker must not mutate the task world
            if self._pre_checker_fp is not None:
                after_fp = integrity.fingerprint_workdir(self.workdir)
                self.integrity_mutations = integrity.apply_integrity_flag(
                    evidence, before=self._pre_checker_fp, after=after_fp
                )
            self.evidence = evidence
            loop_store.write_evidence(self.loop_dir, self.tick, evidence)
            # Gate inputs: Claim + Evidence only (truth-blind; no candidates/Σ)
            gate_args = {
                "claim": self.claim,
                "evidence": evidence,
                "quota": dict(self.quota),
                "repair_counts": {},
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
                cur = self.tree.in_progress() or self.tree.root
                await self.request(
                    stage="veto",
                    request_prefix=topics.ROLE_VERIFIER_RUN,
                    result_prefix=topics.ROLE_VERIFIER_RESULT,
                    payload={
                        "args": {
                            "tick": self.tick,
                            "loop_dir": str(self.loop_dir),
                            "subgoal_id": cur.id,
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
            self.tree.admit_current()
            loop_store.save_tree(self.loop_dir, self.tree)
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
        active_len = len(sigma.load_active(self.workdir))
        if decide_refiner(decision=kind, active_len=active_len, focus_score=self.focus_score):
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
                    }
                },
            )
            return
        # Skip refiner; maybe still veto
        if kind == "admit" and should_veto_after_admit(self.evidence):
            cur = self.tree.in_progress() if self.tree else None
            await self.request(
                stage="veto",
                request_prefix=topics.ROLE_VERIFIER_RUN,
                result_prefix=topics.ROLE_VERIFIER_RESULT,
                payload={
                    "args": {
                        "tick": self.tick,
                        "loop_dir": str(self.loop_dir),
                        "subgoal_id": cur.id if cur else "root",
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
        }
        if kind == "abort":
            await self.finish(ok=False, error=str(self.decision.get("reason") or "abort"), answer=answer)
            return
        if kind == "repair":
            answer["rolled_back"] = True
        await self.finish(ok=True, answer=answer)

    async def on_finished(
        self, *, ok: bool, error: str | None = None, answer: Any = None
    ) -> None:
        self.outcome = {"ok": ok, "error": error, "answer": answer}
