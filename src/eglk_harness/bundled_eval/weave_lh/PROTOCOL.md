# Weave LH PROTOCOL

1. `fetch_lh_eval.sh` → `vendor/LongHorizon-Harness/eval/WeaveBench-harness`
2. Materialize task via `eglk-harness eval --suite weave_lh --prepare-only`
3. Run harness (`eglk-harness run` or LH cua-harness) **outside** Gate
4. Produce judge JSON → `--external-score` → Manifest only

## Forbidden

- Feeding Weave pass_rate into Gate / Evidence / Claim admit authority
- Treating Weave absolute score as eglk primary scientific claim (WA-Hard is main ruler)
