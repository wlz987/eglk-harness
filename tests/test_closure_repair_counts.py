"""Closure repair counts toward repairs_max (regression for reducer kernel-3)."""

from __future__ import annotations

import unittest

from eglk_harness.domain.event_store import EventEnvelope
from eglk_harness.domain.kernel.reducer import apply_event, empty_projection
from eglk_harness.domain.kernel.repair_counts import closure_repair_key


def _ev(seq: int, type_: str, payload: dict) -> EventEnvelope:
    return EventEnvelope(
        schema="eglk.event",
        event_id=f"e{seq}",
        sequence=seq,
        prev_hash=None if seq == 0 else "sha256:" + "0" * 64,
        hash="sha256:" + "1" * 64,
        type=type_,
        occurred_at="2026-01-01T00:00:00Z",
        payload=payload,
    )


class ClosureRepairCountTests(unittest.TestCase):
    def test_closure_repair_increments_repair_counts(self) -> None:
        state = empty_projection()
        state.nodes["root"] = type(state.nodes.get("root")) if "root" in state.nodes else None
        from eglk_harness.domain.kernel.reducer import NodeState

        state.nodes["root"] = NodeState(id="root", title="root", status="pending")
        apply_event(
            state,
            _ev(
                0,
                "GateDecided",
                {
                    "schema": "eglk.gate_decision",
                    "decision": "repair",
                    "reason": "closure_incomplete",
                    "node_id": "root",
                    "contract_ref": "wc-root",
                    "satisfied_obligation_ids": [],
                    "open_obligation_ids": ["ob-1"],
                    "is_closure_gate": True,
                },
            ),
        )
        key = closure_repair_key()
        self.assertEqual(state.repairs_used, 1)
        self.assertEqual(state.repair_counts.get(key), 1)


if __name__ == "__main__":
    unittest.main()
