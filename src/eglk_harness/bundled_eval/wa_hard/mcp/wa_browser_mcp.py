"""Playwright browser MCP for WA-Hard official HAR path (web automation, not desktop AT-SPI).

Writes ``agent_runs/<task_id>/network.har`` + ``agent_response.json`` under WA_BROWSER_WORKDIR.
Scores never feed Gate — official eval-tasks runs externally.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

WORKDIR = Path(os.environ.get("WA_BROWSER_WORKDIR", ".")).resolve()
TASK_ID = os.environ.get("WA_BROWSER_TASK_ID", "").strip()
HEADED = os.environ.get("WA_BROWSER_HEADED", "").strip().lower() in {"1", "true", "yes", "on"}

server = MCPServer(
    "wa-browser",
    instructions=(
        "WebArena browser tools for WA-Hard official HAR path. "
        "Call wa_start_session first. Navigate/click/fill against start_urls. "
        "When done, wa_write_agent_response (official JSON schema) then wa_finalize_session."
    ),
)

_playwright: Any = None
_browser: Browser | None = None
_context: BrowserContext | None = None
_page: Page | None = None
_har_path: Path | None = None
_task_id: str = ""


def _run_dir(task_id: str) -> Path:
    return WORKDIR / "agent_runs" / task_id


def _safe_path(rel: str) -> Path:
    path = (WORKDIR / rel).resolve()
    if not str(path).startswith(str(WORKDIR)):
        raise ValueError(f"path escapes workdir: {rel}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


async def _ensure_page() -> Page:
    global _page
    if _page is not None:
        return _page
    if _context is None:
        raise RuntimeError("call wa_start_session before other browser tools")
    _page = await _context.new_page()
    return _page


@server.tool()
async def wa_start_session(task_id: str = "") -> str:
    """Start a HAR-recording browser session for one WA task."""
    global _playwright, _browser, _context, _page, _har_path, _task_id
    tid = (task_id or TASK_ID).strip()
    if not tid:
        raise ValueError("task_id required (arg or WA_BROWSER_TASK_ID)")
    _task_id = tid
    run_dir = _run_dir(tid)
    run_dir.mkdir(parents=True, exist_ok=True)
    _har_path = run_dir / "network.har"
    if _context is not None:
        await _context.close()
        _context = None
        _page = None
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=not HEADED)
    _context = await _browser.new_context(
        record_har_path=str(_har_path),
        viewport={"width": 1280, "height": 800},
    )
    return json.dumps(
        {
            "ok": True,
            "task_id": tid,
            "har_path": str(_har_path.relative_to(WORKDIR)),
            "run_dir": str(run_dir.relative_to(WORKDIR)),
        }
    )


@server.tool()
async def wa_navigate(url: str) -> str:
    """Navigate to a URL (records network events into network.har)."""
    page = await _ensure_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    return json.dumps({"ok": True, "url": page.url, "title": await page.title()})


@server.tool()
async def wa_snapshot() -> str:
    """Return URL, title, and HTML excerpt of the current page."""
    page = await _ensure_page()
    html = await page.content()
    return json.dumps(
        {
            "ok": True,
            "url": page.url,
            "title": await page.title(),
            "html_excerpt": html[:16000],
        }
    )


@server.tool()
async def wa_click(selector: str) -> str:
    """Click an element matching the CSS selector."""
    page = await _ensure_page()
    await page.click(selector, timeout=20000)
    return json.dumps({"ok": True, "selector": selector, "url": page.url})


@server.tool()
async def wa_fill(selector: str, value: str) -> str:
    """Fill an input or select matching the CSS selector."""
    page = await _ensure_page()
    loc = page.locator(selector).first
    tag = await loc.evaluate("el => el.tagName.toLowerCase()")
    if tag == "select":
        await loc.select_option(value)
    else:
        await loc.fill(value, timeout=20000)
    return json.dumps({"ok": True, "selector": selector, "value": value, "tag": tag})


@server.tool()
async def wa_screenshot(path: str = "wa_screenshot.png") -> str:
    """Capture screenshot with real_browser provenance meta."""
    page = await _ensure_page()
    png = _safe_path(path)
    await page.screenshot(path=str(png), full_page=True)
    meta = {
        "capture_source": "real_browser",
        "engine": "playwright-chromium",
        "suite": "wa_hard",
        "task_id": _task_id,
        "headed": HEADED,
        "url": page.url,
        "title": await page.title(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "path": str(png.relative_to(WORKDIR)),
    }
    meta_path = Path(str(png) + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return json.dumps({"ok": True, "path": str(png.relative_to(WORKDIR)), "meta": meta})


@server.tool()
async def wa_write_agent_response(response_json: str) -> str:
    """Write official agent_response.json for the active task (JSON string)."""
    tid = _task_id or TASK_ID
    if not tid:
        raise ValueError("no active task_id — call wa_start_session first")
    data = json.loads(response_json)
    if not isinstance(data, dict):
        raise ValueError("response_json must be a JSON object")
    out = _run_dir(tid) / "agent_response.json"
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return json.dumps({"ok": True, "path": str(out.relative_to(WORKDIR))})


@server.tool()
async def wa_finalize_session() -> str:
    """Close browser context and flush network.har."""
    global _context, _page, _har_path
    har = str(_har_path) if _har_path else None
    if _context is not None:
        await _context.close()
        _context = None
        _page = None
    return json.dumps({"ok": True, "har_path": har, "task_id": _task_id})


def main() -> None:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
