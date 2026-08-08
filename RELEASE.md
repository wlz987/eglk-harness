# Release checklist · eglk-harness

Version: **0.1.0b1** (empirical eval wiring beta).

## 分发检查（本包）

```bash
cd eglk-harness
make dist-check   # python -m build + twine check (no upload)
```

## Install

```bash
pip install -e .
eglk-harness doctor   # includes eval vendor hints when EGLK_EVAL_ROOT/vendor present
# when published: uv tool install eglk-harness
```

发布前另请确认：`eglk-harness check-projections`、`eglk-harness --help`、`eglk-harness eval --help`。

## Optional PyPI publish (manual)

1. Bump `pyproject.toml` / `__version__` / CHANGELOG.
2. `python -m build && twine check dist/*`
3. `twine upload dist/*` (credentials required).

## Live / full benchmark matrix

全量 WA / Weave / OSWorld / TB 矩阵由工作区 `experiment/eval` 驱动；需 operator 在
`$EGLK_EVAL_ROOT/vendor/` 提供 vendor 树（不随包分发）。评测分数 **never feed Gate**。
