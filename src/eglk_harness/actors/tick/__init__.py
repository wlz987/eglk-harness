"""TickJob — one tick: maker → apply → checker → gate → tree/world post."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eba_job import Job

from eglk_harness.domain import loop_store, worldref
from eglk_harness.domain.tree import TaskTree, make_root
from eglk_harness.protocol import topics


def _stage_err(body: Any) -> str | None:
    if not isinstance(body, dict):
        return "non_dict_result"
    if body.get("ok") is False:
        return str(body.get("error") or "stage_failed")
    return None


class TickJob(Job):
    """Single-tick stage machine (M2: no SWARM / refiner yet)."""

    def __init__(
        self,
        *,
        workdir: Path,
        goal_id: str,
        tick: int = 0,
        goal_title: str = "goal",
        done_criteria: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.workdir = Path(workdir).resolve()
        self.goal_id = goal_id
        self.tick = int(tick)
        self.goal_title = goal_title
        self.done_criteria = list(done_criteria or ["hello.txt exists"])
        self.loop_dir: Path | None = None
        self.tree: TaskTree | None = None
        self.world: worldref.WorldRef | None = None
        self.claim: dict[str, Any] | None = None
        self.evidence: dict[str, Any] | None = None
        self.decision: dict[str, Any] | None = None
        self.written: list[str] = []
        self.outcome: dict[str, Any] | None = None

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

        cur = tree.in_progress()
        subgoal_id = cur.id if cur else "root"
        await self.request(
            stage="maker",
            request_prefix=topics.ROLE_MAKER_RUN,
            result_prefix=topics.ROLE_MAKER_RESULT,
            payload={
                "args": {
                    "tick": self.tick,
                    "subgoal_id": subgoal_id,
                    "done_criteria": list(cur.done_criteria if cur else self.done_criteria),
                    "goal_id": self.goal_id,
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

        if stage == "maker":
            claim = body.get("claim")
            if not isinstance(claim, dict):
                await self.finish(ok=False, error="maker_missing_claim")
                return
            self.claim = claim
            loop_store.write_claim(self.loop_dir, self.tick, claim)
            try:
                self.written = worldref.apply_claim_payload(
                    self.workdir, claim.get("payload") if isinstance(claim.get("payload"), dict) else None
                )
            except ValueError as exc:
                await self.finish(ok=False, error=f"apply_failed:{exc}")
                return

            cur = self.tree.in_progress()
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
                    }
                },
            )
            return

        if stage == "checker":
            evidence = body.get("evidence")
            if not isinstance(evidence, dict):
                await self.finish(ok=False, error="checker_missing_evidence")
                return
            self.evidence = evidence
            loop_store.write_evidence(self.loop_dir, self.tick, evidence)
            await self.request(
                stage="gate",
                request_prefix=topics.GATE_DECIDE,
                result_prefix=topics.GATE_RESULT,
                payload={
                    "args": {
                        "claim": self.claim,
                        "evidence": evidence,
                        "quota": {"cognitive_tokens": 0},
                        "repair_counts": {},
                    }
                },
            )
            return

        if stage == "gate":
            decision = body.get("decision")
            if not isinstance(decision, dict):
                await self.finish(ok=False, error="gate_missing_decision")
                return
            self.decision = decision
            loop_store.write_decision(self.loop_dir, self.tick, decision)
            await self._post_gate(decision)
            return

        await self.finish(ok=False, error=f"unknown_stage:{stage}")

    async def _post_gate(self, decision: dict[str, Any]) -> None:
        assert self.loop_dir is not None and self.tree is not None
        kind = str(decision.get("decision") or "")
        reason = str(decision.get("reason") or "")

        if kind == "admit":
            self.tree.admit_current()
            loop_store.save_tree(self.loop_dir, self.tree)
            done = self.tree.all_work_admitted()
            loop_store.append_tick_log(
                self.loop_dir,
                {
                    "tick": self.tick,
                    "decision": kind,
                    "reason": reason,
                    "written": list(self.written),
                    "root_done": done,
                },
            )
            await self.finish(
                ok=True,
                answer={
                    "decision": decision,
                    "root_done": done,
                    "written": list(self.written),
                },
            )
            return

        if kind == "repair":
            if self.world is not None:
                self.world = worldref.restore(self.world, self.workdir)
            self.tree.repair_current()
            self.tree.ensure_pointer()
            loop_store.save_tree(self.loop_dir, self.tree)
            loop_store.append_tick_log(
                self.loop_dir,
                {
                    "tick": self.tick,
                    "decision": kind,
                    "reason": reason,
                    "written": list(self.written),
                    "root_done": False,
                },
            )
            await self.finish(
                ok=True,
                answer={
                    "decision": decision,
                    "root_done": False,
                    "rolled_back": True,
                },
            )
            return

        # abort
        self.tree.fail_current()
        loop_store.save_tree(self.loop_dir, self.tree)
        loop_store.append_tick_log(
            self.loop_dir,
            {
                "tick": self.tick,
                "decision": kind or "abort",
                "reason": reason,
                "written": list(self.written),
                "root_done": False,
            },
        )
        await self.finish(
            ok=False,
            error=reason or "abort",
            answer={"decision": decision, "root_done": False},
        )

    async def on_finished(
        self, *, ok: bool, error: str | None = None, answer: Any = None
    ) -> None:
        self.outcome = {"ok": ok, "error": error, "answer": answer}
