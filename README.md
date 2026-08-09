# eglk-harness

独立可安装包：**Evidence-Gated Loop Kernel** harness（机械 Gate · 零 HITL · Maker≠Checker）。

包布局：`protocol/` ⊥ `domain/` ⊥ `actors/`，仅 `app.py` 组合根。  
勿与用户 workdir 下的 **`.eglk-harness/`**（运行配置/工件）混淆。

## Install

```bash
pip install -e .
eglk-harness doctor
# when published: uv tool install eglk-harness
```

发布前分发检查见 [`RELEASE.md`](./RELEASE.md) · 当前版本 **0.1.0b1**。

## Quick start

```bash
cd /path/to/your/project
eglk-harness init
# edit .goal.md — add verifiable done criteria
eglk-harness run --agent mock --compile auto
eglk-harness status          # read-only; no approval UI
eglk-harness status --json   # machine-readable (still RO / zero HITL)
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
| `doctor` | PATH / schemas / skills / MCP / `host_tick_timeout` / eval vendor hints；`--json`；`--install-codex-gui` 显式装插件 |
| `run` | STEP 0 compile → four-phase tick |
| `status` | Read-only tree / decision count / tick·focus·unc (signal) / quota / leaf；`--json` |
| `dashboard` | Read-only HTTP browse（无 approve/inject） |
| `check-update` | PyPI version hint（不自动升级） |
| `plugin` | `list`/`install`/`uninstall` computer-use（**run 永不自动装**） |
| `eval` | 辅尺：`EGLK_EVAL_ROOT`（如 `experiment/eval`）动态加载 `lib/`；scorer **不进 Gate**（见 [`docs/KERNEL_VS_EVAL.md`](./docs/KERNEL_VS_EVAL.md)） |
| `soak-bypass` | 旁路角色 LLM soak（Governor/E/V/Refiner/compile；无工具） |
| `check-projections` | 常量钉扎 vs `domain/kernel/projections.py` |

`run` flags: `--goal/--task`, `--agent`, `--model`, `--maker-model`, `--checker-model`, `--maker-timeout`, `--checker-timeout`, `--workdir`, `--mcp-config`, `--mcp-add-dir`, `--swarm`, `--compile`, `--dashboard`（只读观测，非审批闸）.

配置优先级：**CLI > `.eglk-harness/config.toml` > `.env`/环境变量 > 内置默认**（`run` 启动时 bootstrap）。

Eval Manifests land under workdir `.local/runs/<run_id>/` (gitignored).  
设置 `EGLK_EVAL_ROOT=experiment/eval`（pack、`lib/` 套件连接器、`skills/` overlay）。
