"""Environment package."""

from eglk_harness.domain.environment.base import Environment, ExecResult
from eglk_harness.domain.environment.local import LocalEnvironment, default_environment

__all__ = ["Environment", "ExecResult", "LocalEnvironment", "default_environment"]
