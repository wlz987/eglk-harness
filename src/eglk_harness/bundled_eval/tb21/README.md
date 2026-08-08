# tb21 · Terminal-Bench 2.1（LH 覆盖辅尺）

LH 论文报 Terminal-Bench 2.1，但 LH `eval/` **无**冻结 TB 树。本 suite 为 pack-first 薄接线。

```bash
eglk-harness eval --suite tb21 --list-tasks
bash experiment/eval/scripts/run_tb21_smoke.sh
```

分数仅 Manifest；见 `PROTOCOL.md` / `FULL_REPRO.md` / `../LH_PARITY.md`。
