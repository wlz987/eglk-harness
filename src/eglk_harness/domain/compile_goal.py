"""STEP 0: compile ``.goal.md`` → ``.goal_format.md``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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


def _mock_format(goal_text: str) -> str:
    title = "Goal"
    for line in goal_text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            title = s.lstrip("#").strip() or title
            break
    return (
        f"# Goal Format\n\n"
        f"> Compiled abstract frame (STEP 0). No concrete subtask split.\n\n"
        f"## Direction\n\n"
        f"Pursue: {title}\n\n"
        f"## Constraints\n\n"
        f"- Preserve `.goal.md` and `.eglk-harness/`.\n"
        f"- Prefer verifiable done criteria from the human goal.\n"
    )


def compile_goal(
    workdir: Path,
    *,
    mode: str | None = None,
    backend: str = "mock",
    binary_present: bool | None = None,
) -> CompileResult:
    """Compile or reuse ``.goal_format.md``.

    ``auto``/``force`` fail hard when backend binary missing (unless backend=mock).
    ``off`` is the only skip path.
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

    # live backends require CLI
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

    text = _mock_format(goal.read_text(encoding="utf-8"))
    if not text.strip():
        return CompileResult(None, "error", "empty compile output")
    out.write_text(text, encoding="utf-8")
    return CompileResult(out, "wrote", f"mode={mode_s} backend={backend}")
