"""RunHost — adopts ``eglk.run.start``; Job construction injected by app."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from eba import Envelope
from eba_job import Job, JobHost

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
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.job_factory = job_factory
        self.workdir = Path(workdir).resolve()
        self.goal_id = goal_id
        self.goal_title = goal_title
        self.done_criteria = list(done_criteria or ["hello.txt exists"])
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
        )
        self.jobs.append(job)
        return job

    async def on_start(self) -> None:
        await self.bus.subscribe(topics.RUN_START, self.inbox)

    async def on_own(self, envelope: Envelope[Any]) -> None:
        if envelope.header.topic == topics.RUN_START:
            await self.adopt_and_begin(envelope)
