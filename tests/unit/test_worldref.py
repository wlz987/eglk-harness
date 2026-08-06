from pathlib import Path

import pytest

from eglk_harness.domain.worldref import (
    apply_claim_payload,
    apply_files,
    restore,
    snapshot_workdir,
)


def test_snapshot_apply_restore(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "a.txt").write_text("v1", encoding="utf-8")
    snaps = tmp_path / "snaps"
    ref = snapshot_workdir(work, snaps / "pre_000", revision=0, tick=0)
    assert ref.revision == 0
    assert (ref.snapshot / "a.txt").read_text(encoding="utf-8") == "v1"

    apply_files(work, {"a.txt": "v2", "b.txt": "new"})
    assert (work / "a.txt").read_text(encoding="utf-8") == "v2"
    assert (work / "b.txt").read_text(encoding="utf-8") == "new"

    restored = restore(ref, work)
    assert restored.revision == 1
    assert (work / "a.txt").read_text(encoding="utf-8") == "v1"
    assert not (work / "b.txt").exists()


def test_apply_rejects_path_escape(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    try:
        apply_files(work, {"../x.txt": "no"})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "escape" in str(e)


def test_apply_refuses_protected(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / ".goal.md").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="protected path"):
        apply_claim_payload(work, {"files": {".goal.md": "hack", "ok.txt": "yes"}})
    assert (work / ".goal.md").read_text(encoding="utf-8") == "keep"
    assert not (work / "ok.txt").exists()


def test_snapshot_ignores_harness_dir(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "a.txt").write_text("x", encoding="utf-8")
    harness = work / ".eglk-harness"
    harness.mkdir()
    (harness / "secret").write_text("no", encoding="utf-8")
    ref = snapshot_workdir(work, tmp_path / "pre", revision=1, tick=1)
    assert not (ref.snapshot / ".eglk-harness").exists()
    assert (ref.snapshot / "a.txt").exists()


def test_apply_skips_text_placeholder_over_png(tmp_path: Path) -> None:
    work = tmp_path / "work"
    pack = work / "evidence_pack"
    pack.mkdir(parents=True)
    png = pack / "shot.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 100)
    written = apply_files(work, {"evidence_pack/shot.png": "[binary screenshot, 181731 bytes]"})
    assert written == []
    assert png.read_bytes().startswith(b"\x89PNG")
