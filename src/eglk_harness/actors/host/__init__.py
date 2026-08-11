"""RunHost — adopts ``eglk.run.start``; Job construction injected by app."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from eba import Envelope
from eba_job import Job, JobHost

from eglk_harness.domain.kernel.goal_parse import INTENT_CRITERIA_FALLBACK
from eglk_harness.protocol import topics

JobFactory = Callable[..., Job]

class RunHost(JobHost[Job]):
    """Composition-side host: only routes; no Gate / tree authority.

    ``job_factory`` is supplied by ``app.py`` so this family never imports
    ``actors.tick`` (orthogonality).
    """

    def __init__(
        self,
        *,
        job_factory: JobFactory,
        workdir: Path,
        goal_id: str,
        goal_title: str = "goal",
        done_criteria: list[str] | None = None,
        swarm_soft: str | None = None,
        focus_score: float = 1.0,
        uncertainty: float = 0.0,
        maker_timeout_s: float | None = None,
        checker_timeout_s: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.job_factory = job_factory
        self.workdir = Path(workdir).resolve()
        self.goal_id = goal_id
        self.goal_title = goal_title
        self.done_criteria = list(done_criteria or [INTENT_CRITERIA_FALLBACK])
        self.swarm_soft = swarm_soft
        self.focus_score = float(focus_score)
        self.uncertainty = float(uncertainty)
        self.maker_timeout_s = maker_timeout_s
        self.checker_timeout_s = checker_timeout_s
        self.jobs: list[Job] = []

    def make_job(self, root: Envelope[Any]) -> Job:
        payload = root.payload if isinstance(root.payload, dict) else {}
        args = payload.get("args") if isinstance(payload.get("args"), dict) else payload
        tick = int(args.get("tick", 0))
        job = self.job_factory(
            host=self,
            root=root,
            workdir=self.workdir,
            goal_id=str(args.get("goal_id") or self.goal_id),
            tick=tick,
            goal_title=str(args.get("goal_title") or self.goal_title),
            done_criteria=list(args.get("done_criteria") or self.done_criteria),
            swarm_soft=args.get("swarm_soft", self.swarm_soft),
            focus_score=float(args.get("focus_score", self.focus_score)),
            uncertainty=float(args.get("uncertainty", self.uncertainty)),
            quota=dict(args["quota"]) if isinstance(args.get("quota"), dict) else None,
            maker_timeout_s=args.get("maker_timeout_s", self.maker_timeout_s),
            checker_timeout_s=args.get("checker_timeout_s", self.checker_timeout_s),
        )
        self.jobs.append(job)
        return job

    async def on_start(self) -> None:
        await self.bus.subscribe(topics.RUN_START, self.inbox)

    async def on_own(self, envelope: Envelope[Any]) -> None:
        if envelope.header.topic == topics.RUN_START:
            await self.adopt_and_begin(envelope)
