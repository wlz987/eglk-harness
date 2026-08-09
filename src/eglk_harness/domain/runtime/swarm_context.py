"""SWARM prior context: env probes + last Gate decision (never Gate inputs)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def last_gate_decision(loop_dir: Path, tick: int) -> dict[str, Any] | None:
    """Load prior tick Gate decision when resuming tick > 0."""
    if tick <= 0:
        return None
    path = loop_dir / "decisions" / f"{tick - 1:03d}.json"
    if not path.is_file():
        st_path = loop_dir / "state.json"
        if st_path.is_file():
            try:
                st = json.loads(st_path.read_text(encoding="utf-8"))
                ld = st.get("last_decision")
                if isinstance(ld, dict):
                    return ld
            except (OSError, json.JSONDecodeError):
                pass
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def env_probe_priors(workdir: Path) -> list[dict[str, Any]]:
    """Manifest-only eval probes as prior_evidence (scores never Gate)."""
    eval_root = (os.environ.get("EGLK_EVAL_ROOT") or "").strip()
    if not eval_root:
        return []
    try:
        from eglk_harness.domain.eval.loader import load_env_probes_module

        mod = load_env_probes_module(Path(eval_root))
    except Exception:
        return []
    priors: list[dict[str, Any]] = []
    wa_cfg = os.environ.get("WA_HARD_CONFIG") or ""
    if hasattr(mod, "probe_wa_sites"):
        try:
            sites = mod.probe_wa_sites(Path(wa_cfg) if wa_cfg else None)
            if isinstance(sites, dict):
                for row in sites.get("sites") or []:
                    if not isinstance(row, dict):
                        continue
                    name = str(row.get("name") or "")
                    url = str(row.get("url") or "")
                    ok = row.get("ok")
                    priors.append(
                        {
                            "kind": "env_probe",
                            "ref": f"wa_site:{name}",
                            "text": f"site {name} {url} reachable={ok}",
                        }
                    )
        except Exception:
            pass
    return priors[:12]


def scout_observation_priors(workdir: Path, tick: int) -> list[dict[str, Any]]:
    """Summarize prior-tick scout JSON under .eglk-harness/scout/ for leaf contract."""
    scout_root = workdir / ".eglk-harness" / "scout"
    tick_dir = scout_root / f"tick_{max(0, tick - 1):03d}"
    if not tick_dir.is_dir():
        return []
    priors: list[dict[str, Any]] = []
    for path in sorted(tick_dir.glob("scout_snapshot_*.json"))[-2:]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        url = str(data.get("url") or "")
        title = str(data.get("title") or "")
        links = data.get("links") if isinstance(data.get("links"), list) else []
        sample = [
            f"{l.get('text', '')[:40]} → {l.get('href', '')}"
            for l in links[:6]
            if isinstance(l, dict)
        ]
        priors.append(
            {
                "kind": "scout_obs",
                "ref": path.name,
                "text": f"scout {url} «{title}» links_sample: " + "; ".join(sample),
            }
        )
    return priors
