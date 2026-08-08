# Release checklist · eglk-harness

Version: **0.1.0b1** (empirical eval wiring beta).

## Local release-check

```bash
cd eglk-harness
make release-check
make dist-check   # python -m build + twine check (no upload)
```

Runs: pytest · projections · soak-bypass mock · maturity_gate · packaging metadata.

## Install

```bash
pip install -e ".[dev]"
eglk-harness doctor   # includes eval vendor hints when EGLK_EVAL_ROOT/vendor present
# when published: uv tool install eglk-harness
```

## Optional PyPI publish (manual)

1. Bump `pyproject.toml` / `__version__` / CHANGELOG.
2. `python -m build && twine check dist/*`
3. `twine upload dist/*` (credentials required).

## Live / full benchmark runs

Live Weave/OSWorld/WA/TB matrix runs require operator-provided vendor trees under
`$EGLK_EVAL_ROOT/vendor/` (not bundled). Scores from eval **never feed Gate**.

```bash
# Optional: point at an external eval asset tree
export EGLK_EVAL_ROOT=/path/to/eval-assets

# Long natural split (live Codex; ≥30min or tree split)
bash scripts/run_long_natural_split.sh

# Live long maturity lane (vLLM :28000)
bash scripts/run_live_long_maturity.sh
```
