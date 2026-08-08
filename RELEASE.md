# Release checklist · eglk-harness

Version: **0.1.0b1** (empirical eval wiring beta).

## Local release-check

在同级目录 [`eglk-harness_test`](../eglk-harness_test) 中运行：

```bash
cd ../eglk-harness_test
pip install -e ../eglk-harness -e .
make release-check
```

在实现包中仅做分发检查：

```bash
cd eglk-harness
make dist-check   # python -m build + twine check (no upload)
```

`release-check` 在 `eglk-harness_test` 中运行（单元测试 · projections · soak-bypass mock · maturity_gate · CLI 契约）。

## Install

```bash
pip install -e .
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

手动成熟度脚本见 `eglk-harness_test/scripts/`（如 `run_long_natural_split.sh`）。
