"""STEP 0: compile ``.goal.md`` → ``.goal_format.md``."""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GOAL_FORMAT_NAME = ".goal_format.md"


@dataclass
class CompileResult:
    path: Path | None
    action: str  # reused | wrote | skipped | error
    detail: str = ""


def resolve_compile_mode(cli: str | None = None, *, env: dict[str, str] | None = None) -> str:
    env = env or os.environ
    raw = (cli or env.get("EGLK_COMPILE") or "auto").strip().lower()
    if raw not in {"auto", "force", "off"}:
        raise ValueError(f"invalid compile mode: {raw!r}")
    return raw


def _first_heading(goal_text: str) -> str:
    for line in goal_text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip() or "Goal"
    return "Goal"


def _section_bullets(goal_text: str, *headers: str) -> list[str]:
    want = {h.lower() for h in headers}
    lines = goal_text.splitlines()
    out: list[str] = []
    capture = False
    for line in lines:
        h = re.match(r"^#{1,3}\s+(.+)$", line.strip())
        if h:
            capture = h.group(1).strip().lower() in want
            continue
        if not capture:
            continue
        m = re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$", line)
        if m:
            out.append(m.group(1).strip())
    return out


def _loose_bullets(goal_text: str) -> list[str]:
    return [
        m.group(1).strip()
        for line in goal_text.splitlines()
        if (m := re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$", line))
    ]


def format_goal_frame(goal_text: str) -> str:
    """Build a structured abstract frame from human ``.goal.md`` (no LLM)."""
    title = _first_heading(goal_text)
    criteria = _section_bullets(
        goal_text,
        "acceptance",
        "done",
        "done criteria",
        "success criteria",
        "checklist",
        "验收",
        "完成条件",
    )
    constraints = _section_bullets(
        goal_text, "constraints", "constraint", "边界", "约束", "rules", "non-goals", "non goals"
    )
    if not criteria:
        loose = _loose_bullets(goal_text)
        criteria = loose[:8] if loose else [f"Satisfy the intent of: {title}"]
    if not constraints:
        constraints = [
            "Preserve `.goal.md` and `.eglk-harness/`.",
            "Prefer verifiable done criteria from the human goal.",
        ]

    body_preview = "\n".join(
        ln for ln in goal_text.strip().splitlines() if ln.strip() and not ln.strip().startswith("#")
    )[:800]

    crit_block = "\n".join(f"- {c}" for c in criteria)
    cons_block = "\n".join(f"- {c}" for c in constraints)
    return (
        f"# Goal Format\n\n"
        f"> Compiled abstract frame (STEP 0). No concrete subtask split.\n\n"
        f"## Direction\n\n"
        f"Pursue: {title}\n\n"
        f"## Acceptance (abstract)\n\n"
        f"{crit_block}\n\n"
        f"## Constraints\n\n"
        f"{cons_block}\n\n"
        f"## Source excerpt\n\n"
        f"```\n{body_preview}\n```\n"
    )


def frame_from_compile_json(doc: dict[str, Any], *, source_excerpt: str = "") -> str:
    title = str(doc.get("title") or "Goal")
    direction = str(doc.get("direction") or f"Pursue: {title}")
    acceptance = doc.get("acceptance") or []
    constraints = doc.get("constraints") or []
    if not isinstance(acceptance, list) or not acceptance:
        acceptance = [f"Satisfy the intent of: {title}"]
    if not isinstance(constraints, list) or not constraints:
        constraints = ["Preserve `.goal.md` and `.eglk-harness/`."]
    notes = str(doc.get("notes") or "")
    crit = "\n".join(f"- {c}" for c in acceptance)
    cons = "\n".join(f"- {c}" for c in constraints)
    extra = f"\n## Notes\n\n{notes}\n" if notes else ""
    excerpt = source_excerpt[:800] if source_excerpt else ""
    return (
        f"# Goal Format\n\n"
        f"> Compiled abstract frame (STEP 0 · Adapter). No concrete subtask split.\n\n"
        f"## Direction\n\n"
        f"{direction}\n\n"
        f"## Acceptance (abstract)\n\n"
        f"{crit}\n\n"
        f"## Constraints\n\n"
        f"{cons}\n"
        f"{extra}"
        f"## Source excerpt\n\n"
        f"```\n{excerpt}\n```\n"
    )


async def _compile_via_adapter(workdir: Path, goal_text: str, backend: str) -> str | None:
    from eglk_harness.domain.adapters.factory import create_adapter
    from eglk_harness.domain.runtime.budgets import timeout_for_role
    from eglk_harness.domain.runtime.bypass_llm import run_bypass_json

    adapter = create_adapter(backend)
    raw = await run_bypass_json(
        adapter,
        role="compile",
        workdir=workdir,
        leaf_block=f"[GOAL.md]\n{goal_text[:6000]}",
        extra='JSON: {"title","direction","acceptance":[],"constraints":[],"notes"}',
        tick=0,
        subgoal_id="compile",
        timeout_s=timeout_for_role("compile"),
        force=True,
    )
    if not raw:
        return None
    return frame_from_compile_json(raw, source_excerpt=goal_text)


def _run_compile_coro(factory: Any) -> str | None:
    """Run Adapter compile from sync code; safe under a running event loop.

    ``factory`` is a zero-arg callable returning the awaitable.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(factory())
        except Exception:
            return None
    # Nested loop (e.g. app_run already async): isolate in a worker thread.
    import concurrent.futures

    def _in_thread() -> str | None:
        try:
            return asyncio.run(factory())
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_in_thread).result(timeout=200)


def compile_goal(
    workdir: Path,
    *,
    mode: str | None = None,
    backend: str = "mock",
    binary_present: bool | None = None,
) -> CompileResult:
    """Compile or reuse ``.goal_format.md``.

    Live backends: try Adapter compile session (no tools); on failure fall back
    to mechanical ``format_goal_frame`` (still writes). Missing binary → hard error.
    """
    workdir = workdir.resolve()
    goal = workdir / ".goal.md"
    out = workdir / GOAL_FORMAT_NAME
    mode_s = resolve_compile_mode(mode)

    if mode_s == "off":
        return CompileResult(out if out.is_file() else None, "skipped", "compile=off")

    if not goal.is_file():
        return CompileResult(None, "error", "missing .goal.md")

    if mode_s == "auto" and out.is_file():
        if out.stat().st_mtime >= goal.stat().st_mtime:
            return CompileResult(out, "reused", "goal_format newer-or-equal")

    goal_text = goal.read_text(encoding="utf-8")
    source = "mechanical"

    if backend not in {"mock", "fake"}:
        present = binary_present
        if present is None:
            import shutil

            present = shutil.which("codex" if backend == "codex" else "claude") is not None
        if not present:
            return CompileResult(
                None,
                "error",
                f"compile backend {backend!r} missing from PATH (no silent fallback)",
            )
        use_llm = (os.environ.get("EGLK_COMPILE_LLM") or "1").strip().lower() not in {
            "0",
            "off",
            "false",
        }
        if use_llm:
            llm_text = _run_compile_coro(lambda: _compile_via_adapter(workdir, goal_text, backend))
            if llm_text and llm_text.strip():
                text = llm_text
                source = "adapter"
            else:
                text = format_goal_frame(goal_text)
                source = "mechanical_fallback"
        else:
            text = format_goal_frame(goal_text)
    else:
        # mock: still exercise adapter compile path when EGLK_COMPILE_LLM=1
        use_llm = (os.environ.get("EGLK_COMPILE_LLM") or "1").strip().lower() not in {
            "0",
            "off",
            "false",
        }
        if use_llm:
            llm_text = _run_compile_coro(lambda: _compile_via_adapter(workdir, goal_text, "mock"))
            text = llm_text or format_goal_frame(goal_text)
            source = "adapter" if llm_text else "mechanical"
        else:
            text = format_goal_frame(goal_text)

    if not text.strip():
        return CompileResult(None, "error", "empty compile output")
    out.write_text(text, encoding="utf-8")
    return CompileResult(out, "wrote", f"mode={mode_s} backend={backend} source={source}")
