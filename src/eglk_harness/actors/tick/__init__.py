"""TickJob — thin EBA Job adapter over kernel ``TickRunLoop``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eba import ErrBody, OkBody
from eba_job import Job

from eglk_harness.domain.kernel.run_loop import TickRunLoop


class TickJob(Job, TickRunLoop):
    """One tick = Phase 0→1→2→3. Registered via ``RunEngine.tick_job_factory()``."""

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
        TickRunLoop.__init__(
            self,
            workdir=workdir,
            goal_id=goal_id,
            tick=tick,
            goal_title=goal_title,
            done_criteria=done_criteria,
            swarm_soft=swarm_soft,
            focus_score=focus_score,
            uncertainty=uncertainty,
            quota=quota,
            maker_timeout_s=maker_timeout_s,
            checker_timeout_s=checker_timeout_s,
        )

    async def begin(self) -> None:
        await TickRunLoop.begin(self)

    async def on_stage_result(self, stage: str, body: OkBody | ErrBody) -> None:
        await TickRunLoop.on_stage_result(self, stage, body)

    async def finish(
        self, *, ok: bool, error: str | None = None, answer: Any = None
    ) -> None:
        # Publish outcome before ``finished`` so run loop cannot miss ``root_done``.
        self.outcome = {"ok": ok, "error": error, "answer": answer}
        await super().finish(ok=ok, error=error, answer=answer)

    async def on_finished(
        self, *, ok: bool, error: str | None = None, answer: Any = None
    ) -> None:
        self.outcome = {"ok": ok, "error": error, "answer": answer}
