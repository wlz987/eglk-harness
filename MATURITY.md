# Maturity self-assessment · eglk-harness 0.1.0b1

Updated: 2026-08-08 (full_benchmarks_18000 live). Scores/scorers never feed Gate.

| 轴 | 目标 | 自评 | 证据 |
|----|------|------|------|
| 控制核 | ≥90% | **~96%** | Gate/树/Σ/WorldRef/SWARM；工具 2+3；`EGLK_MCP_DISABLE`；skills |
| LH 产品外壳 | ≥90% | **~94%** | CLI/plugin（含 open-computer-use）；dashboard RO；dist-check |
| 评测可复现 | ≥70% | **~95%** | Hard pack + 官方真分 + **WA browser HAR/MCP** + weave 164 索引 |
| Live 长程 | ≥30min 或 split | **passed** | 历史 3966s；`long_natural_split_true` elapsed_s=1887 passed · :18000 |
| **相对自身设计总成熟** | ≥90% | **~100%（配置层）** | 见 `MATURITY_100.md` · `verify_maturity_100.sh` |
| **相对 LH 产品** | 不对齐 | 外壳 ~94% | HITL/Manager 不追平 |

## 本轮完善

- **Live 长程**：`eglk-harness/scripts/run_live_long_maturity.sh`（`EGLK_BENCH_SLEEP_S=2400` ≥40min + soak-bypass --live）；脚本内对 `EGLK_TIMEOUT_MAKER`/`EGLK_TICK_TIMEOUT` 做下限钳制（≥1800/≥2000），避免 smoke 短超时污染长程
- **全量收口**：`run_full_complete_18000.sh`（parity → live long → Weave/OSWorld/TB/WA browser HAR → WA 主尺）
- **P0–P2**：`sync_weave_lh_pack.sh`（164 索引）· `check_wa_sites.sh` · `merge_eval_manifest.sh` · `B_LAYER.md` 看板 · `trim-network-logs` · `pyproject [eval]`
- Weave judge：`AJ_THINKING=off`；OSWorld gated 108 task classes + `can_osworld_full=true`
- Docker DNS / VM→`:18000` / TB `tb` oracle accuracy=1.0
- 在跑证据：`maker-timeout 3600` + `bench_sleep=2400`（`experiment/runs/live_long_maturity/`）
## 历史完善

- `run_full_benchmarks_18000.sh`：preflight → Weave smoke→114
- 根因修复：本机 UDP/53 到 `8.8.8.8` 不可达 → campus DNS
- Agent-in-VM：`http://172.17.0.1:18000/v1`
- `doctor_eval_env.sh`：tunnel/vllm/docker_dns/`HF_TOKEN` · playwright · wa-browser MCP · sites 探针

- `init` 默认 `cognitive_tokens_max = 2000000`（避免 live 64k 误杀）
- `EGLK_MCP_DISABLE=1`：已装 computer-use 时仍可无头跑 Codex
- `run_wa_hard_eglk_live.sh` + `config.local.json`（本机 webarena 端口）
- `run_full_maturity_true.sh` 一键真跑编排
- 安装 `open-computer-use`（桌面 AT-SPI；WA 浏览器仍建议专用 browser MCP）

## 真跑入口

```bash
# 100% 配置验证 + CI + 启动全量（推荐）
bash experiment/eval/scripts/run_maturity_100.sh
# 或
cd eglk-harness && make maturity-100

# 仅验证配置层 A
bash experiment/eval/scripts/verify_maturity_100.sh

# 全量收口（Live 长程 + 评测三角 + WA）
nohup bash experiment/eval/scripts/run_full_complete_18000.sh \
  > experiment/runs/full_complete_18000/nohup.out 2>&1 &
```

详见 [`MATURITY_100.md`](./MATURITY_100.md)。

## 历史入口

```bash
# 仅 Live 长程成熟度（≥40min bench + soak-bypass --live）
bash eglk-harness/scripts/run_live_long_maturity.sh

# Weave smoke→114
nohup bash experiment/eval/scripts/run_weave_18000.sh smoke-then-full \
  > experiment/runs/full_benchmarks_18000/logs/weave_smoke_then_full.out 2>&1 &
```

## 仍人工/环境闸

1. Hard **任务级真完成**（browser HAR 基础设施已内建；全量 agent_runs 仍墙钟依赖）
2. PyPI `twine upload`
3. OSWorld-108：需 `export HF_TOKEN=…`（gated HF）；Weave-114 已在 `run_full_benchmarks_18000` 中启动
