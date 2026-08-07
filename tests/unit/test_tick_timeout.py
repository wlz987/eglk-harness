"""Tick host timeout override (EGLK_TICK_TIMEOUT)."""

from __future__ import annotations


from eglk_harness.app import _request_timeout


def test_tick_timeout_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("EGLK_TICK_TIMEOUT", "2400")
    assert _request_timeout("codex") == 2400.0
    monkeypatch.setenv("EGLK_TICK_TIMEOUT", "30")
    assert _request_timeout("mock") == 30.0
    monkeypatch.delenv("EGLK_TICK_TIMEOUT", raising=False)
    assert _request_timeout("mock") == 30.0
    assert _request_timeout("codex") == 600.0
