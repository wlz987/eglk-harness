# Maturity self-assessment · eglk-harness 0.1.0b1

Updated: 2026-08-07 (full_maturity_true sweep). Scores/scorers never feed Gate.

| 轴 | 目标 | 自评 | 证据 |
|----|------|------|------|
| 控制核 | ≥90% | **~96%** | Gate/树/Σ/WorldRef/SWARM；工具 2+3；`EGLK_MCP_DISABLE`；skills |
| LH 产品外壳 | ≥90% | **~94%** | CLI/plugin（含 open-computer-use）；dashboard RO；dist-check |
| 评测可复现 | ≥70% | **~93%** | Hard pack + 官方真分路径 + **sites 真起 + eglk live 剧本**；LH 三角 A/B/FULL playbook |
| Live 长程 | ≥30min 或 split | **passed + 再跑中** | 历史 3966s；`long_natural_split_true` nohup（1800s bench · :18000） |
| **相对自身设计总成熟** | ≥90% | **~96%** | 工程路径闭合；Hard 官方 agent_logs/浏览器轨迹仍在真跑中 |
| **相对 LH 产品** | 不对齐 | 外壳 ~94% | HITL/Manager 不追平 |

## 本轮完善

- `init` 默认 `cognitive_tokens_max = 2000000`（避免 live 64k 误杀）
- `EGLK_MCP_DISABLE=1`：已装 computer-use 时仍可无头跑 Codex
- `run_wa_hard_eglk_live.sh` + `config.local.json`（本机 webarena 端口）
- `run_full_maturity_true.sh` 一键真跑编排
- 安装 `open-computer-use`（桌面 AT-SPI；WA 浏览器仍建议专用 browser MCP）

## 真跑入口

```bash
# 日志：experiment/runs/full_maturity_true_logs/
bash experiment/eval/scripts/run_full_maturity_true.sh
# 或已在跑的 long / WA：
tail -f experiment/runs/full_maturity_true_logs/long2.out
tail -f experiment/runs/full_maturity_true_logs/wa_eglk_live2.out
```

## 仍人工/环境闸

1. Hard **官方** `agent_response.json`+`network.har` 浏览器轨迹（open-computer-use ≠ 网页自动化）
2. PyPI `twine upload`
3. Weave-114 / OSWorld-108 上游全量（资产下载已 nohup；VM/API 仍外置）
