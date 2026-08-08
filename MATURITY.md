# Maturity · eglk-harness

Engineering gates for the **standalone** package.

## CI-safe (default)

```bash
make release-check    # pytest + projections + soak mock + eval_compare
make maturity         # same via scripts/maturity_gate.sh
eglk-harness check-projections
```

## Manual live lanes

| Lane | Script | Notes |
|------|--------|-------|
| Natural long split | `scripts/run_long_natural_split.sh` | Live Codex; ≥30min or tree split |
| Live long maturity | `scripts/run_live_long_maturity.sh` | vLLM `:28000` + soak-bypass `--live` |
| Demo GIF | `scripts/generate_demo_gif.sh` | `docs/site/assets/` under this repo |

Run artifacts land under `runs/` (gitignored) or operator-chosen `LONG_RUN_DIR`.

## Eval assets

- Bundled: `src/eglk_harness/bundled_eval/` (example packs + fixtures)
- Override: `EGLK_EVAL_ROOT` (same directory layout)
- Live vendors: `$EGLK_EVAL_ROOT/vendor/` (operator-provided; not shipped)

Scores from eval **never feed Gate**.
