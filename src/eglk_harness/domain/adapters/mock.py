"""Mock AgentAdapter for tests and offline ``--agent mock`` runs."""

from __future__ import annotations

import json
from typing import Any

from eglk_harness.domain.adapters.base import EpisodeRequest, EpisodeResult


class MockAdapter:
    """Scripted Maker/Checker responses — no subprocess / LLM."""

    name = "mock"

    def __init__(self, *, mode: str = "admit") -> None:
        self.mode = mode  # admit | repair_integrity | repair_empty

    async def run_episode(self, request: EpisodeRequest) -> EpisodeResult:
        tick = int(request.meta.get("tick", 0))
        subgoal_id = str(request.meta.get("subgoal_id") or "root")
        written = list(request.meta.get("written") or [])

        if request.role == "maker" or request.expect == "claim":
            claim = self._claim(tick, subgoal_id)
            text = json.dumps(claim, ensure_ascii=False)
            return EpisodeResult(ok=True, text=text, parsed=claim, backend=self.name)

        if request.role == "checker" or request.expect == "evidence":
            evidence = self._evidence(tick, subgoal_id, written)
            text = json.dumps(evidence, ensure_ascii=False)
            return EpisodeResult(ok=True, text=text, parsed=evidence, backend=self.name)

        if request.role == "governor":
            doc = {
                "split_node": subgoal_id,
                "children": [
                    {
                        "id": f"{subgoal_id}.01",
                        "title": f"Implement {subgoal_id}",
                        "done_criteria": ["implementation complete"],
                    },
                    {
                        "id": f"{subgoal_id}.02",
                        "title": f"Verify {subgoal_id}",
                        "done_criteria": ["verification evidence recorded"],
                    },
                ],
            }
            return EpisodeResult(ok=True, text=json.dumps(doc), parsed=doc, backend=self.name)

        if request.role == "explorer":
            doc = {
                "alternatives": [
                    {"id": "alt-1", "text": "direct implement", "prob": 0.8, "impact": 0.9},
                    {"id": "alt-2", "text": "incremental", "prob": 0.5, "impact": 0.6},
                    {"id": "alt-3", "text": "cosmetic only", "prob": 0.1, "impact": 0.05},
                ]
            }
            return EpisodeResult(ok=True, text=json.dumps(doc), parsed=doc, backend=self.name)

        if request.role == "verifier":
            doc = {
                "challenges": [
                    {"id": "ch-1", "title": "missing artifact", "text": "ensure deliverable exists"},
                ],
                "veto": False,
            }
            return EpisodeResult(ok=True, text=json.dumps(doc), parsed=doc, backend=self.name)

        if request.role == "refiner":
            doc = {
                "id": f"sigma-hit-{tick:03d}",
                "kind": "hit",
                "text": "mock refined hit",
                "conf": 0.75,
            }
            return EpisodeResult(ok=True, text=json.dumps(doc), parsed=doc, backend=self.name)

        if request.role == "compile":
            doc = {
                "title": "Mock Goal",
                "direction": "Pursue mock goal",
                "acceptance": ["mock acceptance"],
                "constraints": ["Preserve .eglk-harness/"],
                "notes": "mock compile",
            }
            return EpisodeResult(ok=True, text=json.dumps(doc), parsed=doc, backend=self.name)

        return EpisodeResult(
            ok=False,
            error=f"mock unsupported role/expect: {request.role}/{request.expect}",
            backend=self.name,
        )

    def _claim(self, tick: int, subgoal_id: str) -> dict[str, Any]:
        if self.mode == "repair_empty":
            return {
                "claim_id": f"claim-{tick:03d}",
                "tick": tick,
                "maker_session_id": "mock-maker",
                "kind": "files",
                "done_progress": 1.0,
                "confidence": 0.9,
                "alternatives": [{"text": "noop", "status": "reject", "reason": "worse"}],
                "payload": {"files": {}},
                "step_review": {
                    "gains": ["empty payload for repair path"],
                    "losses": ["no durable artifact"],
                    "benefits": ["exercises no_evidence_grounding"],
                    "risks": ["should not admit"],
                },
                "shortcut_hit": False,
                "subgoal_id": subgoal_id,
            }
        content = "tampered\n" if self.mode == "repair_integrity" else "hello from mock maker\n"
        return {
            "claim_id": f"claim-{tick:03d}",
            "tick": tick,
            "maker_session_id": "mock-maker",
            "kind": "files",
            "done_progress": 1.0,
            "confidence": 0.95,
            "alternatives": [
                {"text": "leave file unchanged", "status": "reject", "reason": "incomplete"},
            ],
            "payload": {"files": {"hello.txt": content}},
            "step_review": {
                "gains": ["wrote hello.txt via payload.files"],
                "losses": ["skipped broader packaging"],
                "benefits": ["leaf can be audited by file presence"],
                "risks": ["content may be wrong relative to acceptance"],
            },
            "shortcut_hit": False,
            "subgoal_id": subgoal_id,
        }

    def _evidence(self, tick: int, subgoal_id: str, written: list[str]) -> dict[str, Any]:
        if self.mode == "repair_integrity":
            return {
                "evidence_id": f"ev-{tick:03d}",
                "tick": tick,
                "checker_session_id": "mock-checker",
                "audit_progress": 1.0,
                "audit_confidence": 0.9,
                "gaps": [],
                "alternatives": [],
                "alternatives_missing": False,
                "challenges": [],
                "cost_usd": 0.0,
                "artifacts": [f"observed:{p}" for p in written] or ["observed:hello.txt"],
                "integrity_violation": True,
                "criteria_defect": False,
                "subgoal_id": subgoal_id,
            }
        if self.mode == "repair_empty" or not written:
            return {
                "evidence_id": f"ev-{tick:03d}",
                "tick": tick,
                "checker_session_id": "mock-checker",
                "audit_progress": 0.0,
                "audit_confidence": 0.5,
                "gaps": ["no artifacts on disk"],
                "alternatives": [],
                "alternatives_missing": False,
                "challenges": [],
                "cost_usd": 0.0,
                "artifacts": [],
                "integrity_violation": False,
                "criteria_defect": False,
                "subgoal_id": subgoal_id,
            }
        return {
            "evidence_id": f"ev-{tick:03d}",
            "tick": tick,
            "checker_session_id": "mock-checker",
            "audit_progress": 1.0,
            "audit_confidence": 0.95,
            "gaps": [],
            "alternatives": [],
            "alternatives_missing": False,
            "challenges": [],
            "cost_usd": 0.0,
            "artifacts": [f"observed:{p}" for p in written],
            "integrity_violation": False,
            "criteria_defect": False,
            "subgoal_id": subgoal_id,
        }
