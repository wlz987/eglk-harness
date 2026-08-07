"""PyPI update check (informational only — never auto-upgrade)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from eglk_harness import __version__

_PYPI_JSON = "https://pypi.org/pypi/eglk-harness/json"
_PACKAGE = "eglk-harness"


@dataclass(frozen=True)
class UpdateCheckResult:
    package: str
    current: str
    latest: str | None
    update_available: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "package": self.package,
            "current": self.current,
            "latest": self.latest,
            "update_available": self.update_available,
            "detail": self.detail,
            "auto_upgrade": False,
            "read_only": True,
        }


def check_update(*, timeout_s: float = 10.0) -> UpdateCheckResult:
    """Compare installed version to PyPI latest. Network failure → soft warn."""
    current = __version__
    try:
        with urllib.request.urlopen(_PYPI_JSON, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        latest = str(payload.get("info", {}).get("version") or "")
        if not latest:
            return UpdateCheckResult(
                _PACKAGE, current, None, False, "PyPI response missing version"
            )
        newer = _is_newer(latest, current)
        detail = (
            f"update available: {current} → {latest}"
            if newer
            else f"up to date ({current})"
            if latest == current or not newer
            else f"installed {current}; PyPI latest {latest}"
        )
        return UpdateCheckResult(_PACKAGE, current, latest, newer, detail)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return UpdateCheckResult(
                _PACKAGE,
                current,
                None,
                False,
                f"package not yet on PyPI (local {current})",
            )
        return UpdateCheckResult(_PACKAGE, current, None, False, f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return UpdateCheckResult(_PACKAGE, current, None, False, f"check failed: {exc}")


def _is_newer(latest: str, current: str) -> bool:
    def parts(v: str) -> tuple:
        out: list = []
        for chunk in v.replace("-", ".").split("."):
            if chunk.isdigit():
                out.append(int(chunk))
            else:
                out.append(chunk)
        return tuple(out)

    try:
        return parts(latest) > parts(current)
    except TypeError:
        return latest != current
