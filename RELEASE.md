# Release checklist · eglk-harness

Version: **0.1.0b1** (empirical eval wiring beta).

## Local release-check

```bash
cd eglk-harness
make release-check
```

Runs: pytest · projections · soak-bypass mock · maturity_gate (weave + eval_compare) · packaging metadata.

## Install

```bash
pip install -e ".[dev]"
eglk-harness doctor   # includes eval WA/LH vendor hints
# when published: uv tool install eglk-harness
```

## Optional PyPI publish (manual; not part of CI)

1. Bump `pyproject.toml` / `__version__` / CHANGELOG.
2. `python -m build`
3. `twine upload dist/*` (credentials required — do not automate without approval).

## Eval reproducibility

```bash
bash ../experiment/eval/scripts/fetch_lh_eval.sh
bash ../experiment/eval/scripts/fetch_wa_verified.sh
bash ../experiment/eval/scripts/doctor_eval_env.sh
bash ../experiment/eval/scripts/run_weave_lh_smoke.sh
bash ../experiment/eval/scripts/run_osworld_smoke.sh
bash ../experiment/eval/scripts/run_wa_hard_batch.sh
bash scripts/run_long_natural_split.sh   # live Codex; ≥30min or split
```

Scores from eval never feed Gate. See `../experiment/eval/COMPARE_LH.md`.
