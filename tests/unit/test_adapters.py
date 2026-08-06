"""Unit tests for AgentAdapter stack."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.domain.adapters.base import EpisodeRequest, TOOL_ROLES
from eglk_harness.domain.adapters.claude_code import ClaudeCodeAdapter
from eglk_harness.domain.adapters.codex import CodexAdapter
from eglk_harness.domain.adapters.factory import create_adapter
from eglk_harness.domain.adapters.mcp import (
    assert_tools_for_role,
    claude_mcp_argv,
    codex_mcp_argv,
    codex_mcp_overrides,
)
from eglk_harness.domain.adapters.mock import MockAdapter
from eglk_harness.domain.adapters.parse import episode_from_text
from eglk_harness.domain.json_extract import extract_json, unwrap_agent_jsonl
from eglk_harness.domain.schema_validate import parse_and_validate, validate_document
from eglk_harness.domain.skills import load_skill, render_prompt


def test_tool_roles_pin() -> None:
    assert TOOL_ROLES == frozenset({"maker", "checker"})


def test_assert_tools_rejects_governor() -> None:
    with pytest.raises(AssertionError):
        assert_tools_for_role("governor", tools_allowed=True)


def test_episode_request_rejects_mcp_on_swarm_role() -> None:
    with pytest.raises(AssertionError):
        EpisodeRequest(
            role="explorer",
            prompt="x",
            workdir=Path("."),
            tools_allowed=False,
            mcp_config=Path("/tmp/mcp.json"),
        )


def test_codex_mcp_overrides(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        '{"mcpServers":{"computer-use":{"command":"/bin/echo","args":["hi"],"env":{"A":"1"}}}}\n',
        encoding="utf-8",
    )
    overs = codex_mcp_overrides(cfg)
    assert len(overs) == 1
    assert overs[0].startswith("mcp_servers.computer-use=")
    assert "command" in overs[0]


def test_claude_and_codex_argv_empty_without_tools(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp.json"
    cfg.write_text('{"mcpServers":{}}\n', encoding="utf-8")
    assert claude_mcp_argv(mcp_config=cfg, add_dirs=["/x"], tools_allowed=False, role="maker") == []
    assert codex_mcp_argv(mcp_config=cfg, add_dirs=["/x"], tools_allowed=False, role="maker") == []


def test_claude_argv_with_tools(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp.json"
    cfg.write_text('{"mcpServers":{}}\n', encoding="utf-8")
    argv = claude_mcp_argv(
        mcp_config=cfg, add_dirs=["/data"], tools_allowed=True, role="checker"
    )
    assert argv == ["--mcp-config", str(cfg), "--add-dir", "/data"]


def test_extract_json_fenced() -> None:
    text = 'noise\n```json\n{"a": 1}\n```\n'
    assert extract_json(text) == {"a": 1}


def test_extract_json_prefers_claim_object_over_leading_array() -> None:
    text = """
    ["tests/test_store.py", "tests/test_cli.py"]
    ```json
    {
      "claim_id": "c1",
      "tick": 0,
      "maker_session_id": "m",
      "kind": "files",
      "done_progress": 1.0,
      "confidence": 0.9,
      "alternatives": [{"text": "alt", "status": "reject"}],
      "payload": {"files": {}},
      "step_review": {
        "gains": ["parsed claim object"],
        "losses": ["ignored leading path array"],
        "benefits": ["schema-ready claim"],
        "risks": ["array-first stdout still appears"]
      }
    }
    ```
    """
    doc = extract_json(text)
    assert isinstance(doc, dict)
    assert doc["claim_id"] == "c1"


def test_unwrap_codex_jsonl_agent_message() -> None:
    stream = (
        '{"type":"thread.started","thread_id":"t1"}\n'
        '{"type":"item.completed","item":{"id":"item_1","type":"agent_message",'
        '"text":"```json\\n{\\"claim_id\\":\\"c1\\",\\"tick\\":0,\\"maker_session_id\\":\\"m\\",'
        '\\"kind\\":\\"files\\",\\"done_progress\\":1.0,\\"confidence\\":0.9,'
        '\\"alternatives\\":[{\\"text\\":\\"alt\\",\\"status\\":\\"reject\\"}],'
        '\\"payload\\":{\\"files\\":{\\"a.txt\\":\\"x\\"}},'
        '\\"step_review\\":{\\"gains\\":[\\"g\\"],\\"losses\\":[\\"l\\"],'
        '\\"benefits\\":[\\"b\\"],\\"risks\\":[\\"r\\"]}}\\n```"}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":1}}\n'
    )
    body = unwrap_agent_jsonl(stream)
    assert "claim_id" in body
    assert "thread_id" not in body
    doc, errs = parse_and_validate("claim", stream)
    assert errs == []
    assert doc and doc["claim_id"] == "c1"

    ep = episode_from_text(
        EpisodeRequest(
            role="maker",
            prompt="x",
            workdir=Path("."),
            tools_allowed=True,
            expect="claim",
        ),
        stream,
        backend="codex",
    )
    assert ep.ok and ep.parsed and ep.parsed["claim_id"] == "c1"


def test_skills_load() -> None:
    assert "Maker" in load_skill("maker")
    assert "Checker" in load_skill("checker")
    assert "Governor" in load_skill("governor")
    assert "Explorer" in load_skill("explorer")
    prompt = render_prompt("maker", leaf_block="[LEAF]")
    assert "[LEAF]" in prompt
    assert "JSON" in prompt
    assert "step_review" in prompt
    assert "风险" in prompt


@pytest.mark.asyncio
async def test_mock_adapter_claim_and_evidence(tmp_path: Path) -> None:
    ad = MockAdapter(mode="admit")
    claim_ep = await ad.run_episode(
        EpisodeRequest(
            role="maker",
            prompt="x",
            workdir=tmp_path,
            tools_allowed=True,
            expect="claim",
            meta={"tick": 0, "subgoal_id": "root"},
        )
    )
    assert claim_ep.ok and claim_ep.parsed
    errs = validate_document("claim", claim_ep.parsed)
    assert errs == []

    ev_ep = await ad.run_episode(
        EpisodeRequest(
            role="checker",
            prompt="x",
            workdir=tmp_path,
            tools_allowed=True,
            expect="evidence",
            meta={"tick": 0, "subgoal_id": "root", "written": ["hello.txt"]},
        )
    )
    assert ev_ep.ok and ev_ep.parsed
    assert validate_document("evidence", ev_ep.parsed) == []


def test_create_adapter_names() -> None:
    assert create_adapter("mock").name == "mock"
    assert isinstance(create_adapter("codex"), CodexAdapter)
    assert isinstance(create_adapter("claude_code"), ClaudeCodeAdapter)


def test_parse_and_validate_claim() -> None:
    text = """
    Here you go:
    ```json
    {
      "claim_id": "c1",
      "tick": 0,
      "maker_session_id": "m",
      "kind": "files",
      "done_progress": 1.0,
      "confidence": 0.9,
      "alternatives": [{"text": "alt", "status": "reject"}],
      "payload": {"files": {"a.txt": "x"}},
      "step_review": {
        "gains": ["wrote a.txt"],
        "losses": ["no tests"],
        "benefits": ["leaf done criteria closer"],
        "risks": ["content unchecked"]
      }
    }
    ```
    """
    doc, errs = parse_and_validate("claim", text)
    assert errs == []
    assert doc and doc["claim_id"] == "c1"
    assert doc["step_review"]["risks"]


def test_parse_claim_coerces_alt_id_and_timestamp_tick() -> None:
    text = """
    {
      "claim_id": "c1",
      "tick": "2026-08-06T14:20:05Z",
      "maker_session_id": "m",
      "kind": "files",
      "done_progress": 1.0,
      "confidence": 0.9,
      "alternatives": [{"id": "alt_print", "reason": "needs a file"}],
      "payload": {"files": {"a.txt": "x"}},
      "step_review": {
        "得": "wrote file",
        "失": ["skipped other paths"],
        "收益": ["acceptance closer"],
        "风险": "may be wrong"
      }
    }
    """
    doc, errs = parse_and_validate("claim", text)
    assert errs == []
    assert doc is not None
    assert doc["tick"] == 0  # placeholder; MakerActor overwrites with leaf tick
    assert doc["alternatives"][0]["text"] == "alt_print"
    assert doc["alternatives"][0]["status"] == "reject"
    assert doc["step_review"]["gains"] == ["wrote file"]
    assert doc["step_review"]["risks"] == ["may be wrong"]


def test_codex_build_argv_includes_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    fake = tmp_path / "codex"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        '{"mcpServers":{"s":{"command":"echo"}}}\n',
        encoding="utf-8",
    )
    ad = CodexAdapter(mcp_config=cfg, add_dirs=["/extra"])
    argv = ad.build_argv(
        EpisodeRequest(
            role="maker",
            prompt="hi",
            workdir=tmp_path,
            tools_allowed=True,
            mcp_config=cfg,
            add_dirs=("/extra",),
            expect="claim",
        )
    )
    assert "exec" in argv
    assert "-c" in argv
    assert "--add-dir" in argv
    assert argv[-1] == "-"
