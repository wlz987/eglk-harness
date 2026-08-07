# Maturity self-assessment · eglk-harness 0.1.0b1

Updated: 2026-08-07. Workspace: four sibling git repos (`design`/`docs`/`eglk-harness`/`experiment`). Scores/scorers never feed Gate.

| 轴 | 目标 | 自评 | 证据 |
|----|------|------|------|
| 控制核 | ≥90% | ~92% | Gate/树/Σ/WorldRef/SWARM；projections pin；191 tests |
| LH 产品外壳 | ≥90% | ~91% | init/doctor/run/plugin/dashboard RO/`status --json`/`doctor --json`/eval/release-check |
| 评测可复现 | ≥70% | ~80% | HAR-offline；weave/osworld/**tb21** smoke；WA batch；`LH_PARITY.md`；LH vendor 已拉 |
| Live 长程 | 自然 split 或 ≥30min | **passed** | `ACCEPTANCE` ok + elapsed_s=3966（≥30min）；root admit；未触发 split |
| **相对自身设计总成熟** | ≥90% | **~91%** | 长跑达档；主尺 WA-Hard Docker 真分仍外置 |
| **相对 LH 产品完成度** | 不对齐目标 | 外壳 ~91% / 长程与全量评测仍落后 | LH 路线含 HITL+Manager，**不作为 eglk 追平目标** |

## 下一步可完善（按杠杆）

1. **P0** `long_natural_split` ACCEPTANCE ✅（elapsed≈66min；split=False 可接受）
2. **P1** WA-Hard：vendor_ready + NOTES + external-score demo ✅；官方 Docker 真跑仍外置
3. **P1** PyPI 正式发布（按 RELEASE.md，人工）
4. **P2** Weave/OSWorld/**TB2.1** 层 C 全量（env-gated；层 A/B 已绿）
5. **P2** skill 厚度 ✅；Claim final-message 提示已加
6. **P3** 网站/GIF/论文站（非控制核；LH 社区面优势）

## 仍开放

- Weave 全量 114 / OSWorld 全量 / TB 官方 runner：环境剧本已备，不强制本机跑满
- WA-Hard 官方 Docker CLI 真分：vendor_ready；外置执行 + `--external-score`
- PyPI 正式发布：人工步骤见 RELEASE.md

## 一键

```bash
make release-check
make eval-doctor
make eval-smokes
make lh-parity             # LH 三角 + WA 层 A/B
make pulse                 # version / doctor / long ACCEPTANCE (read-only)
make sweep                 # release-check + eval full dry (no long live)
```
