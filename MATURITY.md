# Maturity self-assessment · eglk-harness 0.1.0b1

Updated: 2026-08-07. Scores/scorers never feed Gate.

| 轴 | 目标 | 自评 | 证据 |
|----|------|------|------|
| 控制核 | ≥90% | ~92% | Gate/树/Σ/WorldRef/SWARM；projections pin；176+ tests |
| LH 产品外壳 | ≥90% | ~90% | init/doctor/run/plugin/dashboard RO/eval/release-check |
| 评测可复现 | ≥70% | ~72% | HAR-offline；weave_lh/osworld smoke；WA batch SUMMARY；COMPARE_LH；LH vendor 已拉 |
| Live 长程 | 自然 split 或 ≥30min | 进行中 | `long_natural_split`（1800s bench） |

## 仍开放

- Weave 全量 114 / OSWorld 全量：环境剧本已备，不强制本机跑满
- WA-Hard 官方 Docker CLI 真分：vendor_ready；外置执行 + `--external-score`
- PyPI 正式发布：人工步骤见 RELEASE.md

## 一键

```bash
make release-check
make eval-doctor
make eval-smokes
```
