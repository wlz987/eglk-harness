"""Read-only eval environment probes (Manifest-only scorers; never Gate)."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _count_files(p: Path) -> int:
    if not p.is_dir():
        return 0
    return sum(1 for _ in p.rglob("*") if _.is_file())


def _curl_ok(url: str, timeout_s: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            return 200 <= resp.status < 500
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _tunnel_18000() -> bool:
    try:
        proc = subprocess.run(
            ["ss", "-ltn"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return "0.0.0.0:18000" in (proc.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return False


def _docker_dns_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "alpine:3.20",
                "sh",
                "-c",
                "nslookup archive.ubuntu.com >/dev/null 2>&1",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def count_weave_vendor_tasks(weave_tasks_root: Path) -> int:
    if not weave_tasks_root.is_dir():
        return 0
    n = 0
    for domain_dir in weave_tasks_root.iterdir():
        if not domain_dir.is_dir() or domain_dir.name == "workspace":
            continue
        n += sum(1 for _ in domain_dir.glob("*.md"))
    return n


def probe_wa_sites(config_path: Path | None = None) -> dict[str, Any]:
    """HTTP probe of local WebArena site ports (read-only)."""
    ports: dict[str, str] = {
        "shopping_7770": "http://127.0.0.1:7770",
        "shopping_admin_7780": "http://127.0.0.1:7780/admin",
        "gitlab_8023": "http://127.0.0.1:8023",
        "reddit_9999": "http://127.0.0.1:9999",
        "wikipedia_8888": "http://127.0.0.1:8888",
        "map_3000": "http://127.0.0.1:3000",
    }
    cfg = Path(config_path) if config_path else None
    if cfg and cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            for env_name, env in (data.get("environments") or {}).items():
                urls = env.get("urls") or []
                if urls:
                    ports[str(env_name)] = str(urls[0])
        except (OSError, json.JSONDecodeError):
            pass
    rows: list[dict[str, Any]] = []
    for name, url in ports.items():
        ok = _curl_ok(url, timeout_s=5.0)
        rows.append({"name": name, "url": url, "ok": ok})
    wa_containers: list[str] = []
    if shutil.which("docker"):
        try:
            proc = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            wa_containers = [
                ln for ln in (proc.stdout or "").splitlines() if "webarena" in ln.lower()
            ]
        except (OSError, subprocess.SubprocessError):
            pass
    sites_ok = sum(1 for r in rows if r["ok"])
    return {
        "config": str(cfg) if cfg else None,
        "sites": rows,
        "sites_ok": sites_ok,
        "sites_total": len(rows),
        "wa_containers": wa_containers,
        "can_wa_sites": bool(wa_containers) and sites_ok > 0,
        "note": "read-only probe; scores never Gate",
    }


def collect_eval_env_status(eval_root: Path) -> dict[str, Any]:
    """Full eval environment status (used by doctor_eval_env.sh and doctor CLI)."""
    eval_root = Path(eval_root)
    vendor = eval_root / "vendor"
    lh = vendor / "LongHorizon-Harness" / "eval"
    wa = vendor / "webarena-verified"
    weave = lh / "WeaveBench-harness"
    osw = lh / "OSWorldv2-harness"
    tb = vendor / "terminal-bench"
    weave_tasks = weave / "WeaveBench" / "cache" / "tasks"
    wa_cfg = eval_root / "wa_hard" / "config.local.json"
    wa_mcp = eval_root / "wa_hard" / "mcp" / "wa_browser_mcp.py"
    weave_pack = eval_root / "weave_lh" / "pack.json"
    wa_pack = eval_root / "wa_hard" / "pack.json"

    weave_pack_count = 0
    if weave_pack.is_file():
        try:
            weave_pack_count = len(json.loads(weave_pack.read_text(encoding="utf-8")).get("tasks") or [])
        except (OSError, json.JSONDecodeError):
            pass
    wa_pack_count = 0
    if wa_pack.is_file():
        try:
            wa_pack_count = len(json.loads(wa_pack.read_text(encoding="utf-8")).get("tasks") or [])
        except (OSError, json.JSONDecodeError):
            pass

    playwright_ok = importlib.util.find_spec("playwright") is not None
    mcp_ok = importlib.util.find_spec("mcp") is not None
    kvm = Path("/dev/kvm").exists()
    docker = shutil.which("docker") is not None
    tunnel = _tunnel_18000()
    vllm = _curl_ok("http://127.0.0.1:18000/v1/models")
    docker0 = _curl_ok("http://172.17.0.1:18000/v1/models")
    docker_dns = _docker_dns_ok()
    wa_sites = probe_wa_sites(wa_cfg if wa_cfg.is_file() else None)

    weave_files = _count_files(weave) if weave.is_dir() else 0
    osw_files = _count_files(osw) if osw.is_dir() else 0

    return {
        "eval_root": str(eval_root),
        "docker": docker,
        "kvm": kvm,
        "tunnel_0.0.0.0_18000": tunnel,
        "vllm_127_18000": vllm,
        "vllm_docker0_18000": docker0,
        "docker_dns_ok": docker_dns,
        "playwright_import": playwright_ok,
        "mcp_import": mcp_ok,
        "wa_browser_mcp": wa_mcp.is_file(),
        "wa_config_local": wa_cfg.is_file(),
        "wa_sites_probe_ok": wa_sites.get("can_wa_sites"),
        "wa_sites_detail": wa_sites,
        "wa_verified": wa.is_dir(),
        "wa_files": _count_files(wa) if wa.is_dir() else 0,
        "lh_weave": weave.is_dir(),
        "lh_weave_files": weave_files,
        "lh_weave_task_md": count_weave_vendor_tasks(weave_tasks),
        "weave_lh_pack_count": weave_pack_count,
        "wa_hard_pack_count": wa_pack_count,
        "lh_osworld": osw.is_dir(),
        "lh_osworld_files": osw_files,
        "tb21_vendor": tb.is_dir(),
        "can_wa_live": docker and wa.is_dir(),
        "can_wa_browser_har": playwright_ok and wa_mcp.is_file() and wa_cfg.is_file(),
        "can_weave_smoke": weave.is_dir() and weave_files >= 5 and vllm and docker0 and docker_dns,
        "can_weave_full": kvm and docker and weave.is_dir() and weave_files >= 5 and tunnel and docker_dns,
        "can_osworld_smoke": osw.is_dir() and osw_files >= 5,
        "can_osworld_full": osw.is_dir() and bool(importlib.util.find_spec("huggingface_hub")) and kvm and docker,
        "note": "scores never feed Gate; missing deps → skip not fail",
    }


def doctor_checks_from_status(status: dict[str, Any]) -> list[tuple[str, bool, str]]:
    """Map status dict to (name, ok, detail) tuples for eglk-harness doctor."""
    rows: list[tuple[str, bool, str]] = []
    rows.append(
        (
            "eval_vllm_18000",
            bool(status.get("vllm_127_18000")),
            f"127.0.0.1:18000 ok={status.get('vllm_127_18000')} docker0={status.get('vllm_docker0_18000')}",
        )
    )
    rows.append(
        (
            "eval_tunnel_18000",
            bool(status.get("tunnel_0.0.0.0_18000")),
            "0.0.0.0:18000 bind required for Weave VM",
        )
    )
    rows.append(
        (
            "eval_docker_dns",
            bool(status.get("docker_dns_ok")),
            "campus DNS required on this host (not 8.8.8.8)",
        )
    )
    rows.append(
        (
            "eval_playwright",
            bool(status.get("playwright_import")),
            "pip install eglk-harness[eval] for WA browser HAR",
        )
    )
    rows.append(
        (
            "eval_wa_browser",
            bool(status.get("wa_browser_mcp")) and bool(status.get("wa_config_local")),
            f"mcp={status.get('wa_browser_mcp')} config={status.get('wa_config_local')}",
        )
    )
    sites_ok = bool(status.get("wa_sites_probe_ok"))
    rows.append(
        (
            "eval_wa_sites",
            sites_ok,
            f"sites_ok={status.get('wa_sites_detail', {}).get('sites_ok', 0)}",
        )
    )
    rows.append(
        (
            "eval_weave_pack",
            int(status.get("weave_lh_pack_count") or 0) >= 100,
            f"weave_lh pack tasks={status.get('weave_lh_pack_count')} vendor_md={status.get('lh_weave_task_md')}",
        )
    )
    rows.append(
        (
            "eval_full_readiness",
            bool(status.get("can_weave_full")) and bool(status.get("can_osworld_full")),
            f"weave_full={status.get('can_weave_full')} osworld_full={status.get('can_osworld_full')}",
        )
    )
    return rows
