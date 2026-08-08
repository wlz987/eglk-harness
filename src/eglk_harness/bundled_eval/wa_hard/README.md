# WA-Hard · 主尺评测包

官方 WebArena-Verified **Hard** 题（默认含 Phase-0 `681`/`522`）。

```bash
bash ../scripts/sync_wa_hard_pack.sh          # subset-export → pack.json
bash ../scripts/run_wa_hard_eval_dry.sh       # eval-tasks --dry-run
WA_HARD_LIMIT=3 bash ../scripts/run_wa_hard_batch.sh
eglk-harness eval --suite wa_hard --list-tasks
```

分数仅 Manifest；见 `PROTOCOL.md` / `FULL_REPRO.md`。永不进 Gate。
