# eglk-harness

独立 Git 仓库的可安装实现包（Evidence-Gated Loop Kernel harness）。

设计真相源通常在并列的设计仓 `design/`（本机若与 `alw` 同树：[`../design/`](../design/)）。本仓**不**把设计文档当作实现权威的副本。

包布局：`protocol/` ⊥ `domain/` ⊥ `actors/`，仅 `app.py` 组合根。

```bash
pip install -e ".[dev]"
eglk-harness --help
eglk-harness init
eglk-harness doctor
pytest
```

勿与用户 workdir 下的 **`.eglk-harness/`**（运行配置/工件）混淆。
