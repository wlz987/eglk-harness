# OSWorld aux PROTOCOL

> Auxiliary desktop suite. Offline / external scores → Manifest only. **Never Gate.**

## Flow

1. `fetch_lh_eval.sh` → `vendor/.../OSWorldv2-harness` (or reference fallback)
2. `eglk-harness eval --suite osworld_aux --prepare-only`
3. Run OSWorld / computer-use **outside** eglk Gate
4. `--external-score result.json`

Missing VM/HF/Docker → structured skip (not CI fail).
