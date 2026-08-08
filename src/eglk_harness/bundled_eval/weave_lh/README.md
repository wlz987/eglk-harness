# weave_lh · LH WeaveBench-shaped auxiliary suite

> Scores are Manifest-only — **never** Gate inputs.  
> Full 114-task Weave needs KVM/Docker/API; this pack is for smoke + method wiring.

## Layout

- `pack.example.json` — thin task index
- `fixtures/judge_pass.json` — offline judge stand-in
- See `PROTOCOL.md`

## Run

```bash
# prepare + external score (CI)
eglk-harness eval --suite weave_lh --task-id weave-smoke-001 \
  --eval-root /path/to/alw/experiment/eval --workdir /tmp/weave-lh \
  --external-score fixtures/judge_pass.json --agent mock --prepare-only

# smoke (env-gated)
bash experiment/eval/scripts/run_weave_lh_smoke.sh
```
