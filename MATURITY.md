# Maturity self-assessment · eglk-harness 0.1.0b1

Updated: 2026-08-07. Scores/scorers never feed Gate.

| 轴 | 目标 | 自评 | 证据 |
|----|------|------|------|
| 控制核 | ≥90% | ~92% | Gate/树/Σ/WorldRef/SWARM；projections pin；187 tests |
| LH 产品外壳 | ≥90% | ~91% | init/doctor/run/plugin/dashboard RO/`status --json`/`doctor --json`/eval/release-check |
| 评测可复现 | ≥70% | ~72% | HAR-offline；weave_lh/osworld smoke；WA batch；COMPARE 记分卡；LH vendor 已拉 |
| Live 长程 | 自然 split 或 ≥30min | 重跑中 | parse(Claim-via-cat)+repair tools-off+script freeze；bench 已再启 |
| **相对自身设计总成熟** | ≥90% | **~88–90%**（长跑通过后达档） | 见 `alw/experiment/eval/COMPARE_LH.md` |
| **相对 LH 产品完成度** | 不对齐目标 | 外壳 ~91% / 长程与全量评测仍落后 | LH 路线含 HITL+Manager，**不作为 eglk 追平目标** |

## 仍开放

- Weave 全量 114 / OSWorld 全量：环境剧本已备，不强制本机跑满
- WA-Hard 官方 Docker CLI 真分：vendor_ready；外置执行 + `--external-score`
- PyPI 正式发布：人工步骤见 RELEASE.md

## 一键

```bash
make release-check
make eval-doctor
make eval-smokes
make pulse                 # version / doctor / long ACCEPTANCE (read-only)
```
