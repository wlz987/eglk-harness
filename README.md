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
eglk-harness dashboard       # read-only HTTP; never an approval gate
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
| `doctor` | PATH / schemas / skills / MCP；`--install-codex-gui` 显式装插件 |
| `run` | STEP 0 compile → four-phase tick |
| `status` | Read-only tree / decision / quota / leaf |
| `dashboard` | Read-only HTTP browse（无 approve/inject） |
| `check-update` | PyPI version hint（不自动升级） |
| `eval` | 辅尺：`experiment/eval/` 薄调度；scorer 不进 Gate |
| `soak-bypass` | 旁路角色 LLM soak（Governor/E/V/Refiner/compile；无工具） |
| `check-projections` | CI pin vs `design/kernel/projections.md` |

`run` flags: `--goal/--task`, `--agent`, `--model`, `--maker-model`, `--checker-model`, `--maker-timeout`, `--checker-timeout`, `--workdir`, `--mcp-config`, `--mcp-add-dir`, `--swarm`, `--compile`.

Eval Manifests land under workdir `.local/runs/<run_id>/` (gitignored).  
评测资产 SSOT：设计仓 `experiment/eval/`（主尺 WA-Hard；Weave/OSWorld 辅）。

## Develop

```bash
pytest
eglk-harness check-projections
```
