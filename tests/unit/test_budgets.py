from eglk_harness.domain.budgets import resolve_role_budgets


def test_env_maker_timeout_overrides_default(monkeypatch):
    monkeypatch.setenv("EGLK_TIMEOUT_MAKER", "42")
    budgets = resolve_role_budgets(None, env=dict(**__import__("os").environ))
    assert budgets.maker.max_duration_seconds == 42.0


def test_cli_ns_overrides_env(monkeypatch):
    monkeypatch.setenv("EGLK_TIMEOUT_MAKER", "42")

    class NS:
        maker_timeout = 99.0
        checker_timeout = None

    budgets = resolve_role_budgets(NS(), env=dict(**__import__("os").environ))
    assert budgets.maker.max_duration_seconds == 99.0
