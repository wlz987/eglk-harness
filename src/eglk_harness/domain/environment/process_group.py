"""Guarantee that agent CLIs die with the harness (LH-shaped process group)."""

from __future__ import annotations

import atexit
import os
import signal
import threading
import time

_lock = threading.Lock()
_tracked: set[int] = set()
_installed = False


def track_process_group(pid: int) -> None:
    _install_handlers()
    with _lock:
        _tracked.add(pid)


def untrack_process_group(pid: int) -> None:
    with _lock:
        _tracked.discard(pid)


def signal_process_group(pid: int, sig: int) -> bool:
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True


def kill_process_group(pid: int, *, grace_seconds: float = 1.0) -> None:
    if not signal_process_group(pid, signal.SIGTERM):
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not signal_process_group(pid, 0):
            return
        time.sleep(0.05)
    signal_process_group(pid, signal.SIGKILL)


def kill_all_tracked() -> None:
    with _lock:
        pids = list(_tracked)
        _tracked.clear()
    for pid in pids:
        kill_process_group(pid)


def _install_handlers() -> None:
    global _installed
    with _lock:
        if _installed:
            return
        _installed = True
    atexit.register(kill_all_tracked)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            prev = signal.getsignal(sig)

            def _handler(signum: int, frame: object, *, _prev=prev) -> None:
                kill_all_tracked()
                if callable(_prev):
                    _prev(signum, frame)

            signal.signal(sig, _handler)
        except (ValueError, OSError):
            continue
