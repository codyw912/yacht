"""Parse Codex `exec --json` stdout.

The event types and usage field names come from a captured
`codex exec --json --ephemeral` stream. Skill stages stay empty until
a native skill event is captured.
"""

from __future__ import annotations

import json
from typing import Any


CODEX_JSONL_EVENT_TYPES = frozenset(
    (
        "thread.started",
        "turn.started",
        "item.completed",
        "turn.completed",
        "turn.failed",
        "error",
    )
)


def parse_codex_jsonl(output: str) -> dict[str, Any] | None:
    events = _jsonl_events(output)
    if not events or not _looks_like_codex_jsonl(events):
        return None
    if not any(event.get("type") == "turn.started" for event in events):
        return None
    if not any(
        event.get("type") in {"turn.completed", "turn.failed"} for event in events
    ):
        return None
    usage = _usage(events)
    parsed: dict[str, Any] = {
        "response": _response(events),
        "usage_source": "reported" if usage else "unreported",
        "skill_stages": (),
        "tool_calls": _tool_calls(events),
        "ended": _ended(events),
    }
    if usage:
        parsed["usage"] = usage
    return parsed


def _looks_like_codex_jsonl(events: list[dict[str, Any]]) -> bool:
    return any(event.get("type") in CODEX_JSONL_EVENT_TYPES for event in events)


def _jsonl_events(output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return []
        if not isinstance(event, dict):
            return []
        events.append(event)
    return events


def _response(events: list[dict[str, Any]]) -> str:
    text = ""
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        value = item.get("text")
        if isinstance(value, str):
            text = value
    return text


def _usage(events: list[dict[str, Any]]) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for event in events:
        if event.get("type") != "turn.completed":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        mapping = (
            ("input_tokens", "input_tokens"),
            ("output_tokens", "output_tokens"),
            ("cached_input_tokens", "cache_read_tokens"),
            ("cache_write_input_tokens", "cache_write_tokens"),
        )
        for source, dest in mapping:
            value = usage.get(source)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                parsed[dest] = value
    return parsed


def _ended(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        event_type = event.get("type")
        if event_type in {"turn.failed", "error"}:
            return "error"
        if event_type == "turn.completed":
            return "natural"
    return "unmeasured"


def _tool_calls(events: list[dict[str, Any]]) -> tuple[str, ...]:
    names: list[str] = []
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "command_execution":
            names.append("command_execution")
    return tuple(dict.fromkeys(names))
