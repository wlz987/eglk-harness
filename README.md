# eglk-harness

独立可安装包：**Evidence-Gated Loop Kernel** harness（机械 Gate · 零 HITL · Maker≠Checker）。

设计真相源通常在并列设计仓 [`../design/`](../design/)。包布局：`protocol/` ⊥ `domain/` ⊥ `actors/`，仅 `app.py` 组合根。

勿与用户 workdir 下的 **`.eglk-harness/`**（运行配置/工件）混淆。

## Install

```bash
pip install -e ".[dev]"
eglk-harness doctor
```

## Quick start

```bash
cd /path/to/your/project
eglk-harness init
# edit .goal.md — add verifiable done criteria
eglk-harness run --agent mock --compile auto
eglk-harness status          # read-only; no approval UI
```

Thin wrapper (same as `eglk-harness run`):

```bash
/path/to/eglk-harness/start.sh --agent mock --swarm 0
```

Copy [`env.example`](./env.example) → workdir `.env` for secrets / overrides. Non-secret defaults live in `.eglk-harness/config.toml`.

## CLI

| Command | Role |
|---------|------|
| `init` | Scaffold `.eglk-harness/` + `.goal.md` |
| `doctor` | PATH / schemas / skills / MCP (check-only) |
| `run` | STEP 0 compile → four-phase tick |
| `status` | Read-only tree / decision / quota / leaf |
| `check-projections` | CI pin vs `design/kernel/projections.md` |

`run` flags: `--goal/--task`, `--agent`, `--workdir`, `--mcp-config`, `--mcp-add-dir`, `--swarm`, `--compile`.

Eval Manifests land under workdir `.local/runs/<run_id>/` (gitignored).

## Develop

```bash
pytest
eglk-harness check-projections
```
