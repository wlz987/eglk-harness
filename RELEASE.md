# Release checklist · eglk-harness

## Local release-check

```bash
cd eglk-harness
make release-check
```

Runs: pytest · projections · soak-bypass mock · weave CI · eval_compare · packaging metadata.

## Install (target narrative)

```bash
# editable (dev)
pip install -e ".[dev]"

# tool install (when published)
uv tool install eglk-harness
eglk-harness doctor
```

## Optional PyPI publish (manual; not part of CI)

1. Bump `pyproject.toml` / `__version__` / CHANGELOG.
2. `python -m build`
3. `twine upload dist/*` (requires credentials — **do not** automate in this repo without explicit approval).

## Eval reproducibility

```bash
bash ../experiment/eval/scripts/run_wa_hard_batch.sh
bash ../experiment/eval/scripts/fetch_wa_verified.sh   # optional vendor
bash scripts/run_long_natural_split.sh                 # live Codex
```

Scores from eval never feed Gate.
