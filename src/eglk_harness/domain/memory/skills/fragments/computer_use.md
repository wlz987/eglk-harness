# Computer-use (GUI control)

Use installed computer-use when the leaf contract requires screen interaction, browser automation beyond static fetch, or desktop UI.

## Rules

- Prefer **real screen captures** with provenance (`capture_source=real_screen` or vendor `.meta.json`).
- Hand-written stub files, empty HAR, or placeholder JSON are **not** valid GUI evidence.
- Record `raw_ref` to capture files; Checker must verify structure and non-stub content.
- If GUI tools fail, list gaps as `boundary:` or obligation gaps — do not claim satisfied without attestation.

## Setup (operator, not during `run`)

```bash
eglk-harness plugin list
eglk-harness plugin install --name open-computer-use --agent codex --agent claude_code
# or: eglk-harness doctor --install-codex-gui
```

Set `EGLK_COMPUTER_USE=auto` (default) so Maker/Checker MCP allowlists include the active GUI server.
