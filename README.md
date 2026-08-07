# eglk-harness

独立可安装包：**Evidence-Gated Loop Kernel** harness（机械 Gate · 零 HITL · Maker≠Checker）。

设计真相源通常在并列设计仓 [`../design/`](../design/)。包布局：`protocol/` ⊥ `domain/` ⊥ `actors/`，仅 `app.py` 组合根。

勿与用户 workdir 下的 **`.eglk-harness/`**（运行配置/工件）混淆。

## Install

```bash
pip install -e ".[dev]"
eglk-harness doctor
# when published: uv tool install eglk-harness
```

Release checklist: [`RELEASE.md`](./RELEASE.md) · `make release-check` · version **0.1.0b1**.

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
| `eval` | 辅尺：`experiment/eval/` 薄调度；scorer 不进 Gate |
| `soak-bypass` | 旁路角色 LLM soak（Governor/E/V/Refiner/compile；无工具） |
| `check-projections` | CI pin vs `design/kernel/projections.md` |

`run` flags: `--goal/--task`, `--agent`, `--model`, `--maker-model`, `--checker-model`, `--maker-timeout`, `--checker-timeout`, `--workdir`, `--mcp-config`, `--mcp-add-dir`, `--swarm`, `--compile`, `--dashboard`（只读观测，非审批闸）.

配置优先级（`packaging.md`）：**CLI > `.eglk-harness/config.toml` > `.env`/环境变量 > 内置默认**（`run` 启动时 bootstrap）。

Eval Manifests land under workdir `.local/runs/<run_id>/` (gitignored).  
评测资产 SSOT：设计仓 `experiment/eval/`（主尺 WA-Hard；Weave/OSWorld 辅）。

## Develop

```bash
pytest
eglk-harness check-projections
eglk-harness soak-bypass --agent mock          # CI-safe; llm_roles=5/5
make maturity                                  # pytest + projections + soak + weave CI
make release-check                             # maturity + CLI/version contract
make eval-doctor                               # vendor/docker/kvm readiness JSON
make eval-smokes                               # weave_lh + osworld + wa_hard batch
# Live soak (manual gate):
# EGLK_SOAK_LIVE=1 eglk-harness soak-bypass --agent codex --live --timeout 180
# Eval smoke (from design repo):
# bash experiment/eval/scripts/ci_weave_thin.sh
# bash experiment/eval/scripts/run_wa_hard_batch.sh
# Natural long run (Codex; split or ≥30min):
# bash scripts/run_long_natural_split.sh
# List eval tasks:
# eglk-harness eval --suite wa_hard --list-tasks
# New live run scaffold:
# bash ../experiment/runs/scripts/new_live_run.sh my_run
```

Maturity sheet: [`MATURITY.md`](./MATURITY.md) · LH compare: `../experiment/eval/COMPARE_LH.md`.
