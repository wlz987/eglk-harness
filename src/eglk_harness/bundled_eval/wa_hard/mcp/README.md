# WA browser MCP · Playwright HAR path

专用 **网页** browser MCP（Playwright），不是桌面 `open-computer-use`。

产出官方 `agent_runs/<task_id>/` 树：

- `agent_response.json`
- `network.har`

## 安装

```bash
bash experiment/eval/scripts/install_wa_browser_mcp.sh
cp experiment/eval/wa_hard/config.local.json.example \
   experiment/eval/wa_hard/config.local.json
```

## 运行

```bash
# 官方 vendor demo → eval-tasks（CI 可绿）
bash experiment/eval/scripts/run_wa_hard_browser_har.sh demo

# 真站点 HAR 烟雾（导航 + HAR + eval-tasks）
bash experiment/eval/scripts/run_wa_hard_browser_har.sh har-smoke

# eglk + Codex + wa-browser MCP
WA_BROWSER_MCP=1 EGLK_MCP_DISABLE=0 \
  bash experiment/eval/scripts/run_wa_hard_browser_har.sh live
```

分数 **永不** 进 Gate。见 `FULL_REPRO.md`。
