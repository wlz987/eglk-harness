"""Filesystem layout for workdir / .eglk-harness."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.kernel.projections import STATE_SCHEMA as STATE_SCHEMA  # re-export

HARNESS_DIRNAME = ".eglk-harness"
LOOP_DIRNAME = "loop"
MEMORY_DIRNAME = "memory"
CONFIG_NAME = "config.toml"
GOAL_NAME = ".goal.md"


def harness_root(workdir: Path) -> Path:
    return workdir / HARNESS_DIRNAME


def loop_root(workdir: Path) -> Path:
    return harness_root(workdir) / LOOP_DIRNAME


def memory_root(workdir: Path) -> Path:
    return harness_root(workdir) / MEMORY_DIRNAME


def config_path(workdir: Path) -> Path:
    return harness_root(workdir) / CONFIG_NAME


def goal_path(workdir: Path) -> Path:
    return workdir / GOAL_NAME


def loop_goal_dir(workdir: Path, goal_id: str) -> Path:
    return loop_root(workdir) / goal_id


def memory_sigma_dir(workdir: Path) -> Path:
    return memory_root(workdir) / "sigma"


def memory_skills_dir(workdir: Path) -> Path:
    return memory_root(workdir) / "skills"
