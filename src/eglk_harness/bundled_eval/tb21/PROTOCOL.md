# Terminal-Bench 2.1 · PROTOCOL (`tb21`)

1. Pack-first: `tb21/pack.json` (or `pack.example.json`)
2. Optional vendor: `export TB21_VENDOR=/path/to/terminal-bench` or `eval/vendor/terminal-bench/`
3. Materialize: `eglk-harness eval --suite tb21 --prepare-only --task-id …`
4. Run official TB / Harbor runner **outside** Gate
5. Produce judge JSON → `--external-score` → Manifest only

## Forbidden

- Feeding TB pass_rate into Gate / Evidence / Claim admit
- Treating TB absolute score as eglk primary scientific claim (WA-Hard is main ruler)
- Assuming LH `eval/` vendors TB (it does not)
