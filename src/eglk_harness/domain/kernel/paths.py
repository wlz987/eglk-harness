"""Filesystem layout for workdir / .eglk-harness."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.kernel.projections import RUN_PROJECTION_SCHEMA as STATE_SCHEMA  # noqa: F401

HARNESS_DIRNAME = ".eglk-harness"
LOOP_DIRNAME = "loop"
MEMORY_DIRNAME = "memory"
CONFIG_NAME = "config.toml"
CAPABILITY_MANIFEST_NAME = "capability_manifest.json"
GOAL_NAME = ".goal.md"
EVENTS_DB_NAME = "events.db"
PROJECTIONS_DIRNAME = "projections"
CANDIDATES_DIRNAME = "candidates"


def harness_root(workdir: Path) -> Path:
    return workdir / HARNESS_DIRNAME


def loop_root(workdir: Path) -> Path:
    return harness_root(workdir) / LOOP_DIRNAME


def memory_root(workdir: Path) -> Path:
    return harness_root(workdir) / MEMORY_DIRNAME


def config_path(workdir: Path) -> Path:
    return harness_root(workdir) / CONFIG_NAME


def capability_manifest_path(workdir: Path) -> Path:
    return harness_root(workdir) / CAPABILITY_MANIFEST_NAME


def goal_path(workdir: Path) -> Path:
    return workdir / GOAL_NAME


def loop_goal_dir(workdir: Path, goal_id: str) -> Path:
    return loop_root(workdir) / goal_id


def events_db_path(workdir: Path, goal_id: str) -> Path:
    return loop_goal_dir(workdir, goal_id) / EVENTS_DB_NAME


def projections_dir(workdir: Path, goal_id: str) -> Path:
    return loop_goal_dir(workdir, goal_id) / PROJECTIONS_DIRNAME


def candidates_dir(workdir: Path, goal_id: str) -> Path:
    return loop_goal_dir(workdir, goal_id) / CANDIDATES_DIRNAME


def memory_sigma_dir(workdir: Path) -> Path:
    return memory_root(workdir) / "sigma"


def memory_skills_dir(workdir: Path) -> Path:
    return memory_root(workdir) / "skills"


def memory_lifecycle_dirs(workdir: Path) -> dict[str, Path]:
    """Σ isolation lifecycle directories under memory/sigma/."""
    root = memory_sigma_dir(workdir)
    return {
        status: root / status
        for status in ("candidate", "quarantined", "verified", "active", "deprecated")
    }


def ensure_loop_layout(workdir: Path, goal_id: str) -> Path:
    """Create loop layout: events.db parent, projections/, candidates/, world/."""
    root = loop_goal_dir(workdir, goal_id)
    for name in (
        PROJECTIONS_DIRNAME,
        CANDIDATES_DIRNAME,
        "world",
        "sigma",
        "sigma/refined",
        "agent_logs",
    ):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def ensure_memory_layout(workdir: Path) -> Path:
    root = memory_root(workdir)
    for p in memory_lifecycle_dirs(workdir).values():
        p.mkdir(parents=True, exist_ok=True)
    memory_skills_dir(workdir).mkdir(parents=True, exist_ok=True)
    return root
