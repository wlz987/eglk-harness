"""Mock AgentAdapter for tests and offline ``--agent mock`` runs."""

from __future__ import annotations

import json
from typing import Any

from eglk_harness.domain.adapters.base import EpisodeRequest, EpisodeResult
from eglk_harness.domain.kernel import projections as P


class MockAdapter:
    """Scripted Maker/Checker responses — no subprocess / LLM."""

    name = "mock"

    def __init__(self, *, mode: str = "admit") -> None:
        self.mode = mode  # admit | repair_integrity | repair_empty

    async def run_episode(self, request: EpisodeRequest) -> EpisodeResult:
        tick = int(request.meta.get("tick", 0))
        subgoal_id = str(request.meta.get("subgoal_id") or "root")
        written = list(request.meta.get("written") or [])
        contract_ref = str(request.meta.get("contract_ref") or f"wc-{tick:03d}")
        world_rev = int(request.meta.get("world_revision") or 0)
        obligation_ids = [
            str(x) for x in (request.meta.get("obligation_refs") or ["ob-1"]) if str(x).strip()
        ] or ["ob-1"]

        if request.role == "maker" or request.expect == "claim":
            claim = self._claim(tick, subgoal_id, contract_ref=contract_ref, world_rev=world_rev)
            text = json.dumps(claim, ensure_ascii=False)
            return EpisodeResult(ok=True, text=text, parsed=claim, backend=self.name)

        if request.role == "checker" or request.expect == "evidence":
            evidence = self._evidence(
                tick,
                subgoal_id,
                written,
                contract_ref=contract_ref,
                world_rev=world_rev,
                obligation_ids=obligation_ids,
            )
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

    def _claim(
        self,
        tick: int,
        subgoal_id: str,
        *,
        contract_ref: str,
        world_rev: int,
    ) -> dict[str, Any]:
        if self.mode == "repair_empty":
            return {
                "schema": P.ACTION_CLAIM_SCHEMA,
                "claim_id": f"claim-{tick:03d}",
                "contract_ref": contract_ref,
                "maker_session_id": "mock-maker",
                "intent": f"noop for {subgoal_id}",
                "actions": [],
                "alternatives": [{"text": "noop", "status": "reject", "reason": "worse"}],
                "self_assessment": {"done_progress": 1.0, "confidence": 0.9},
                "world_revision_base": world_rev,
                "note": "empty actions for repair path",
            }
        content = "tampered\n" if self.mode == "repair_integrity" else "hello from mock maker\n"
        return {
            "schema": P.ACTION_CLAIM_SCHEMA,
            "claim_id": f"claim-{tick:03d}",
            "contract_ref": contract_ref,
            "maker_session_id": "mock-maker",
            "intent": f"write hello.txt for {subgoal_id}",
            "actions": [
                {
                    "action_id": f"write-hello-{tick:03d}",
                    "kind": "file_write",
                    "side_effect_class": "reversible",
                    "target": "workdir/hello.txt",
                    "payload": {"path": "hello.txt", "content": content},
                }
            ],
            "alternatives": [
                {"text": "leave file unchanged", "status": "reject", "reason": "incomplete"},
            ],
            "self_assessment": {"done_progress": 1.0, "confidence": 0.95},
            "world_revision_base": world_rev,
        }

    def _evidence(
        self,
        tick: int,
        subgoal_id: str,
        written: list[str],
        *,
        contract_ref: str,
        world_rev: int,
        obligation_ids: list[str],
    ) -> dict[str, Any]:
        paths = list(written) or (["hello.txt"] if self.mode == "admit" else [])
        if self.mode == "repair_integrity":
            return {
                "schema": P.EVIDENCE_BUNDLE_SCHEMA,
                "evidence_id": f"ev-{tick:03d}",
                "contract_ref": contract_ref,
                "checker_session_id": "mock-checker",
                "world_revision": world_rev,
                "verdicts": [
                    {
                        "obligation_id": oid,
                        "status": "unsatisfied",
                        "attestations": [],
                        "gaps": ["integrity_violation"],
                        "defect_suspected": False,
                    }
                    for oid in obligation_ids
                ],
                "integrity_violation": True,
                "additional_gaps": [],
            }
        if self.mode == "repair_empty" or not paths:
            return {
                "schema": P.EVIDENCE_BUNDLE_SCHEMA,
                "evidence_id": f"ev-{tick:03d}",
                "contract_ref": contract_ref,
                "checker_session_id": "mock-checker",
                "world_revision": world_rev,
                "verdicts": [
                    {
                        "obligation_id": oid,
                        "status": "unsatisfied",
                        "attestations": [],
                        "gaps": ["no artifacts on disk"],
                        "defect_suspected": False,
                    }
                    for oid in obligation_ids
                ],
                "integrity_violation": False,
                "additional_gaps": [],
            }
        return {
            "schema": P.EVIDENCE_BUNDLE_SCHEMA,
            "evidence_id": f"ev-{tick:03d}",
            "contract_ref": contract_ref,
            "checker_session_id": "mock-checker",
            "world_revision": world_rev,
            "verdicts": [
                {
                    "obligation_id": oid,
                    "status": "satisfied",
                    "attestations": [
                        {
                            "method": "file_exists",
                            "world_revision": world_rev,
                            "digest": f"observed:{p}",
                            "observer": "mock-checker",
                            "raw_ref": p,
                            "watch_set": [p],
                        }
                        for p in paths
                    ],
                    "gaps": [],
                    "defect_suspected": False,
                }
                for oid in obligation_ids
            ],
            "integrity_violation": False,
            "additional_gaps": [],
        }
