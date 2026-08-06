"""Normalized reads of agent CLI stdout (Codex JSON / Claude stream-json).

Three views: visible assistant text, ordered steps, runtime signal labels.
Format detection lives here so call sites do not re-derive it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

CLAUDE_STREAM_JSON = "claude_stream_json"
CODEX_EXEC_JSON = "codex_exec_json"
CHAT_JSONL = "chat_jsonl"
UNKNOWN = ""

TURN_FAILED_SIGNAL = "AGENT_TURN_FAILED"

_CODEX_EVENTS = {
    "thread.started",
    "turn.started",
    "turn.completed",
    "turn.failed",
    "item.started",
    "item.updated",
    "item.completed",
}
_CLAUDE_EVENTS = {"system", "assistant", "user", "result"}
_CODEX_TOOL_ITEMS = {
    "command_execution",
    "file_change",
    "mcp_tool_call",
    "dynamic_tool_call",
    "collab_tool_call",
    "web_search",
    "todo_list",
}


def detect_format(raw: str) -> str:
    saw_chat_role = False
    for record in _json_records(raw):
        record_type = record.get("type")
        if record_type in _CODEX_EVENTS:
            return CODEX_EXEC_JSON
        if record_type in _CLAUDE_EVENTS:
            return CLAUDE_STREAM_JSON
        if _chat_message(record) is not None:
            saw_chat_role = True
    return CHAT_JSONL if saw_chat_role else UNKNOWN


def visible_output(raw: str) -> str:
    """Best-effort readable text from Adapter stdout (NDJSON or plain)."""
    if not raw or not raw.strip():
        return ""
    log_format = detect_format(raw)
    if log_format == CODEX_EXEC_JSON:
        texts = _codex_assistant_texts(raw)
        if texts:
            return "\n".join(texts).strip()
    elif log_format == CLAUDE_STREAM_JSON:
        result_text, assistant_texts = _claude_texts(raw)
        if result_text.strip():
            return result_text.strip()
        if assistant_texts:
            return "\n\n".join(assistant_texts).strip()
    elif log_format == CHAT_JSONL:
        texts = _chat_assistant_texts(raw)
        if texts:
            return texts[-1].strip()
    # Legacy fallback: scan all known event shapes
    chunks: list[str] = []
    for record in _json_records(raw):
        text = _from_codex_event(record) or _from_claude_event(record)
        if text:
            chunks.append(text)
    if chunks:
        return "\n".join(chunks)
    return raw.strip()


def iter_steps(raw: str) -> list[dict[str, Any]]:
    """Ordered UI-friendly steps; alias of parse_trajectory with message kind."""
    steps = parse_trajectory(raw)
    # Plan A1 expects kind=="message" for assistant prose in minimal fixtures
    out: list[dict[str, Any]] = []
    for step in steps:
        kind = step.get("kind")
        if kind == "text":
            out.append({**step, "kind": "message"})
        else:
            out.append(step)
    return out


def parse_trajectory(raw: str) -> list[dict[str, Any]]:
    log_format = detect_format(raw)
    if log_format == CODEX_EXEC_JSON:
        return _codex_trajectory(raw)
    if log_format == CLAUDE_STREAM_JSON:
        return _claude_trajectory(raw)
    return []


def runtime_signal_labels(raw: str) -> list[str]:
    """Labels for crash / turn-failed detection (dashboard / diagnostics)."""
    labels: list[str] = []
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("AGENT_EXIT=") or stripped.startswith("AGENT_TURN_FAILED"):
            labels.append(stripped.split(":", 1)[0].split("=", 1)[0])
    for record in _json_records(raw):
        if record.get("type") == "turn.failed":
            labels.append(TURN_FAILED_SIGNAL)
        if record.get("type") == "error":
            labels.append("AGENT_ERROR")
        if record.get("type") == "result" and record.get("is_error"):
            labels.append("AGENT_RESULT_ERROR")
    # Preserve order, unique
    seen: set[str] = set()
    out: list[str] = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


def tool_output_view(raw: str) -> str:
    """Tool/command output plus non-JSON lines, for crash detection."""
    log_format = detect_format(raw)
    parts: list[str] = []
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("{"):
            parts.append(line)
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            parts.append(line)
            continue
        if not isinstance(record, dict):
            continue
        if log_format == CODEX_EXEC_JSON:
            parts.extend(_codex_tool_output(record))
        elif log_format == CLAUDE_STREAM_JSON:
            parts.extend(_claude_tool_output(record))
    return "\n".join(part for part in parts if part)


def write_visible_sidecar(tee_path: str | None, raw: str) -> str | None:
    """Write ``*.visible.txt`` next to a tee trajectory; return path or None."""
    paths = write_trajectory_sidecars(tee_path, raw)
    return paths.get("visible")


def write_trajectory_sidecars(tee_path: str | None, raw: str) -> dict[str, str]:
    """Write visible.txt and steps.json beside a tee file; return written paths."""
    if not tee_path:
        return {}
    from eglk_harness.domain.runtime.redact import redact_secrets

    src = Path(tee_path)
    if src.name.endswith(".jsonl"):
        base = src.with_name(src.name[: -len(".jsonl")])
    else:
        base = src.with_suffix("") if src.suffix else src

    out: dict[str, str] = {}
    text = redact_secrets(visible_output(raw))
    if text.strip():
        visible = Path(str(base) + ".visible.txt")
        visible.parent.mkdir(parents=True, exist_ok=True)
        visible.write_text(text + "\n", encoding="utf-8")
        out["visible"] = str(visible)

    steps = iter_steps(raw)
    if steps:
        steps_path = Path(str(base) + ".steps.json")
        steps_path.parent.mkdir(parents=True, exist_ok=True)
        steps_path.write_text(json.dumps(steps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out["steps"] = str(steps_path)
    return out


# ----------------------------------------------------------------------------
# Codex
# ----------------------------------------------------------------------------


def _codex_assistant_texts(raw: str) -> list[str]:
    texts: list[str] = []
    for record in _json_records(raw):
        if record.get("type") != "item.completed":
            continue
        item = record.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text)
    return texts


def _codex_tool_output(record: dict[str, Any]) -> list[str]:
    record_type = record.get("type")
    if record_type == "turn.failed":
        error = record.get("error")
        message = error.get("message") if isinstance(error, dict) else None
        return [f"{TURN_FAILED_SIGNAL}: {message or 'codex turn failed'}"]
    if record_type == "error":
        message = record.get("message")
        return [str(message)] if message else []
    if record_type not in {"item.completed", "item.updated"}:
        return []
    item = record.get("item")
    if not isinstance(item, dict):
        return []
    item_type = item.get("type")
    if item_type == "command_execution":
        output = item.get("aggregated_output")
        return [str(output)] if output else []
    if item_type == "mcp_tool_call":
        text, _ = _content_blocks_to_text(_codex_mcp_content(item))
        return [text] if text else []
    if item_type == "error":
        message = item.get("message")
        return [str(message)] if message else []
    return []


def _codex_trajectory(raw: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    started_ids: set[str] = set()
    for record in _json_records(raw):
        record_type = record.get("type")
        if record_type == "thread.started":
            steps.append(
                {
                    "kind": "session",
                    "model": "codex",
                    "cwd": "",
                    "mcp_servers": [],
                    "tool_count": 0,
                    "thread_id": record.get("thread_id", ""),
                }
            )
            continue
        if record_type == "error":
            message = record.get("message")
            if message:
                steps.append(_tool_result_step("", str(message), [], True))
            continue
        if record_type == "turn.failed":
            error = record.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            steps.append({"kind": "result", "text": str(message or "codex turn failed"), "is_error": True})
            continue
        if record_type == "turn.completed":
            steps.append(_codex_result_step(record, steps))
            continue
        if record_type not in {"item.started", "item.completed"}:
            continue
        item = record.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        item_id = str(item.get("id") or "")
        if item_type == "agent_message":
            text = item.get("text")
            if record_type == "item.completed" and isinstance(text, str) and text.strip():
                steps.append({"kind": "text", "text": text})
            continue
        if item_type == "reasoning":
            text = item.get("text") or "\n".join(
                part for part in (item.get("summary") or []) if isinstance(part, str)
            )
            if record_type == "item.completed" and isinstance(text, str) and text.strip():
                steps.append({"kind": "thinking", "text": text})
            continue
        if item_type == "error":
            if record_type == "item.completed":
                steps.append(_tool_result_step(item_id, str(item.get("message") or ""), [], True))
            continue
        if item_type not in _CODEX_TOOL_ITEMS:
            continue
        if record_type == "item.started" or item_id not in started_ids:
            started_ids.add(item_id)
            steps.append(_codex_tool_use_step(item_id, item_type, item))
        if record_type == "item.completed":
            result = _codex_tool_result_step(item_id, item_type, item)
            if result is not None:
                steps.append(result)
    return steps


def _codex_tool_use_step(item_id: str, item_type: str, item: dict[str, Any]) -> dict[str, Any]:
    if item_type == "command_execution":
        return {"kind": "tool_use", "id": item_id, "name": "shell", "input": {"command": item.get("command", "")}}
    if item_type == "file_change":
        return {"kind": "tool_use", "id": item_id, "name": "apply_patch", "input": {"changes": item.get("changes") or []}}
    if item_type == "mcp_tool_call":
        name = f"{item.get('server', '')}/{item.get('tool', '')}".strip("/")
        arguments = item.get("arguments")
        return {
            "kind": "tool_use",
            "id": item_id,
            "name": name or "mcp",
            "input": arguments if isinstance(arguments, dict) else {"arguments": arguments},
        }
    if item_type == "web_search":
        return {"kind": "tool_use", "id": item_id, "name": "web_search", "input": {"query": item.get("query", "")}}
    if item_type == "todo_list":
        return {"kind": "tool_use", "id": item_id, "name": "todo_list", "input": {"items": item.get("items") or []}}
    payload = {key: value for key, value in item.items() if key not in {"id", "type", "status"}}
    return {"kind": "tool_use", "id": item_id, "name": item_type, "input": payload}


def _codex_tool_result_step(item_id: str, item_type: str, item: dict[str, Any]) -> dict[str, Any] | None:
    failed = str(item.get("status") or "") == "failed"
    if item_type == "command_execution":
        exit_code = item.get("exit_code")
        text = str(item.get("aggregated_output") or "")
        if exit_code is not None:
            text = f"{text}\n[exit_code={exit_code}]".strip()
        return _tool_result_step(item_id, text, [], failed or bool(exit_code))
    if item_type == "file_change":
        changes = item.get("changes") or []
        lines = [
            f"{change.get('kind', '')} {change.get('path', '')}".strip()
            for change in changes
            if isinstance(change, dict)
        ]
        return _tool_result_step(item_id, "\n".join(lines), [], failed)
    if item_type == "mcp_tool_call":
        error = item.get("error")
        if isinstance(error, dict) and error.get("message"):
            return _tool_result_step(item_id, str(error["message"]), [], True)
        text, images = _content_blocks_to_text(_codex_mcp_content(item))
        return _tool_result_step(item_id, text, images, failed)
    if item_type in {"web_search", "todo_list"}:
        return None
    return _tool_result_step(item_id, "", [], failed)


def _codex_mcp_content(item: dict[str, Any]) -> Any:
    result = item.get("result")
    if isinstance(result, dict):
        return result.get("content")
    return None


def _codex_result_step(record: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    final_text = ""
    for step in reversed(steps):
        if step.get("kind") == "text":
            final_text = str(step.get("text") or "")
            break
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
    return {
        "kind": "result",
        "text": final_text,
        "is_error": False,
        "num_turns": 1,
        "input_tokens": usage.get("input_tokens"),
        "cached_input_tokens": usage.get("cached_input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }


# ----------------------------------------------------------------------------
# Claude
# ----------------------------------------------------------------------------


def _claude_texts(raw: str) -> tuple[str, list[str]]:
    result_text = ""
    texts: list[str] = []
    for record in _json_records(raw):
        record_type = record.get("type")
        if record_type == "result" and isinstance(record.get("result"), str):
            result_text = record["result"]
            continue
        if record_type != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        for block in message["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text)
    return result_text, texts


def _claude_tool_output(record: dict[str, Any]) -> list[str]:
    if record.get("type") != "user":
        return []
    message = record.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), list):
        return []
    parts: list[str] = []
    for block in message["content"]:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            text, _ = _content_blocks_to_text(block.get("content"))
            if text:
                parts.append(text)
    return parts


def _claude_trajectory(raw: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for record in _json_records(raw):
        record_type = record.get("type")
        if record_type == "system":
            if record.get("subtype") == "init":
                servers = record.get("mcp_servers") or []
                steps.append(
                    {
                        "kind": "session",
                        "model": record.get("model", ""),
                        "cwd": record.get("cwd", ""),
                        "mcp_servers": [s.get("name") for s in servers if isinstance(s, dict)],
                        "tool_count": len(record.get("tools") or []),
                    }
                )
            continue
        if record_type == "assistant":
            message = record.get("message") if isinstance(record.get("message"), dict) else {}
            for block in message.get("content", []) or []:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "thinking":
                    text = block.get("thinking")
                    if isinstance(text, str) and text.strip():
                        steps.append({"kind": "thinking", "text": text})
                elif block_type == "text":
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        steps.append({"kind": "text", "text": text})
                elif block_type == "tool_use":
                    steps.append(
                        {
                            "kind": "tool_use",
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "input": block.get("input") or {},
                        }
                    )
            continue
        if record_type == "user":
            message = record.get("message") if isinstance(record.get("message"), dict) else {}
            content = message.get("content")
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                text, images = _content_blocks_to_text(block.get("content"))
                steps.append(
                    _tool_result_step(
                        str(block.get("tool_use_id", "")), text, images, bool(block.get("is_error"))
                    )
                )
            continue
        if record_type == "result":
            result_text = record.get("result", "") if isinstance(record.get("result"), str) else ""
            for index in range(len(steps) - 1, -1, -1):
                if steps[index]["kind"] == "text":
                    if steps[index].get("text", "").strip() == result_text.strip():
                        steps.pop(index)
                    break
            steps.append(
                {
                    "kind": "result",
                    "text": result_text,
                    "is_error": bool(record.get("is_error")),
                    "duration_ms": record.get("duration_ms"),
                    "num_turns": record.get("num_turns"),
                    "cost_usd": record.get("total_cost_usd"),
                }
            )
    return steps


# ----------------------------------------------------------------------------
# Chat + shared
# ----------------------------------------------------------------------------


def _chat_message(record: dict[str, Any]) -> dict[str, Any] | None:
    if record.get("type") in _CODEX_EVENTS or record.get("type") in _CLAUDE_EVENTS:
        return None
    message = record.get("message") if isinstance(record.get("message"), dict) else record
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return None
    return message


def _chat_assistant_texts(raw: str) -> list[str]:
    texts: list[str] = []
    for record in _json_records(raw):
        message = _chat_message(record)
        if message is None:
            continue
        text, _ = _content_blocks_to_text(message.get("content"))
        if text.strip():
            texts.append(text)
    return texts


def _json_records(raw: str) -> Iterator[dict[str, Any]]:
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield record


def _tool_result_step(tool_use_id: str, text: str, images: list[str], is_error: bool) -> dict[str, Any]:
    return {
        "kind": "tool_result",
        "tool_use_id": tool_use_id,
        "text": text,
        "images": images,
        "has_image": bool(images),
        "is_error": is_error,
    }


def _content_blocks_to_text(content: Any) -> tuple[str, list[str]]:
    if isinstance(content, str):
        return content, []
    if not isinstance(content, list):
        return ("" if content is None else str(content)), []
    parts: list[str] = []
    images: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif block_type == "image":
            data_url = _image_block_to_data_url(block)
            if data_url:
                images.append(data_url)
                parts.append("[image]")
    return "\n".join(parts), images


def _image_block_to_data_url(block: dict[str, Any]) -> str:
    source = block.get("source") if isinstance(block.get("source"), dict) else block
    data = source.get("data")
    if not isinstance(data, str) or not data:
        return ""
    media_type = source.get("media_type") or source.get("mimeType") or "image/png"
    return f"data:{media_type};base64,{data}"


def _from_codex_event(obj: dict[str, Any]) -> str:
    item = obj.get("item")
    if obj.get("type") == "item.completed" and isinstance(item, dict):
        if item.get("type") == "agent_message":
            return str(item.get("text") or "").strip()
    if obj.get("type") == "agent_message":
        return str(obj.get("text") or "").strip()
    return ""


def _from_claude_event(obj: dict[str, Any]) -> str:
    if obj.get("type") == "assistant" and isinstance(obj.get("message"), dict):
        content = obj["message"].get("content")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            return "".join(parts).strip()
    if obj.get("type") == "content_block_delta":
        delta = obj.get("delta")
        if isinstance(delta, dict) and delta.get("type") == "text_delta":
            return str(delta.get("text") or "")
    return ""
