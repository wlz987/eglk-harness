"""Crash recovery — reconcile dangling transactions (event_store.md)."""

from __future__ import annotations

from typing import Any, Sequence

from eglk_harness.domain.event_store import EventEnvelope
from eglk_harness.domain.kernel.command_handler import CommandHandler


def dangling_transaction_ids(events: Sequence[EventEnvelope]) -> list[str]:
    prepared: dict[str, EventEnvelope] = {}
    settled: set[str] = set()
    for ev in events:
        p = ev.payload or {}
        tid = str(p.get("transaction_id") or "")
        if not tid:
            continue
        if ev.type == "TransactionPrepared":
            prepared[tid] = ev
        elif ev.type in {
            "TransactionCommitted",
            "TransactionRolledBack",
            "TransactionCompensated",
        }:
            settled.add(tid)
    return [tid for tid in prepared if tid not in settled]


def reconcile_dangling_transactions(handler: CommandHandler) -> dict[str, Any]:
    """Roll back prepared-but-unsettled transactions; emit recovery events."""
    events = handler.store.read_all()
    dangling = dangling_transaction_ids(events)
    if not dangling:
        return {"recovered": False, "dangling": []}
    proj = handler.projection()
    if proj.run_status in {"succeeded", "aborted", "invalid", "faulted"}:
        return {"recovered": False, "dangling": dangling, "skipped": "terminal"}
    handler.run_recovery_started("dangling_transactions")
    for tid in dangling:
        handler.transaction_rolled_back(tid)
    handler.run_recovery_completed("running")
    return {"recovered": True, "dangling": dangling}
