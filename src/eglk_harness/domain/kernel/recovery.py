"""Crash recovery — reconcile dangling transactions (event_store.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, Sequence

from eglk_harness.domain.event_store import EventEnvelope
from eglk_harness.domain.kernel.command_handler import CommandHandler


class _RollbackEnv(Protocol):
    def rollback(self, tx: Any, workdir: Path) -> Any: ...


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


def reconcile_dangling_transactions(
    handler: CommandHandler,
    *,
    workdir: Path | None = None,
    env: _RollbackEnv | None = None,
) -> dict[str, Any]:
    """Roll back prepared-but-unsettled transactions; emit recovery events.

    When ``env`` and ``workdir`` are provided, perform physical workdir rollback for
    reversible transactions before recording ``TransactionRolledBack``.
    """
    events = handler.store.read_all()
    dangling = dangling_transaction_ids(events)
    if not dangling:
        return {"recovered": False, "dangling": []}
    proj = handler.projection()
    if proj.run_status in {"succeeded", "aborted", "invalid", "faulted"}:
        return {"recovered": False, "dangling": dangling, "skipped": "terminal"}
    handler.run_recovery_started("dangling_transactions")
    prepared_by_id = {
        str((ev.payload or {}).get("transaction_id") or ""): ev
        for ev in events
        if ev.type == "TransactionPrepared"
    }
    for tid in dangling:
        prep = prepared_by_id.get(tid)
        if prep and workdir is not None and env is not None:
            sec = str((prep.payload or {}).get("side_effect_class") or "reversible")
            if sec == "reversible":
                try:
                    from eglk_harness.domain.environment.world_transaction import WorldTransaction

                    tx = WorldTransaction.from_dict(dict(prep.payload or {}))
                    env.rollback(tx, workdir)
                except (TypeError, ValueError, AttributeError):
                    pass
        handler.transaction_rolled_back(tid)
    reopened = handler.reopen_stranded_in_progress_nodes()
    handler.run_recovery_completed("running")
    return {"recovered": True, "dangling": dangling, "reopened_nodes": reopened}
