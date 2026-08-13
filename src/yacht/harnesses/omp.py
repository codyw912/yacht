"""Parse OMP `--mode json` stdout.

The event types and usage field names come from a captured
`omp -p --mode json --no-session` stream. Skill stages stay empty until
a native skill-prompt event is captured.
"""

from __future__ import annotations

import json
from typing import Any


OMP_JSONL_EVENT_TYPES = frozenset(
    (
        "session",
        "agent_start",
        "turn_start",
        "message_start",
        "message_update",
        "message_end",
        "turn_end",
        "agent_end",
        "tool_execution_start",
        "tool_execution_end",
    )
)
OMP_JSONL_EVIDENCE = "omp-jsonl"

_USAGE_KEYS = (
    ("input", "input_tokens"),
    ("output", "output_tokens"),
    ("cacheRead", "cache_read_tokens"),
    ("cacheWrite", "cache_write_tokens"),
)


def parse_omp_jsonl(output: str) -> dict[str, Any] | None:
    events = _jsonl_events(output)
    if not events or not _looks_like_omp_jsonl(events):
        return None
    if not any(event.get("type") == "agent_start" for event in events):
        return None
    if not any(event.get("type") == "agent_end" for event in events):
        return None

    message = _last_assistant_message(events)
    usage = _usage(message)
    cost = _cost(message)
    parsed: dict[str, Any] = {
        "response": _text_from_message(message),
        "usage_source": "reported" if usage else "unreported",
        "skill_stages": (),
        "tool_calls": _tool_calls(events),
    }
    if usage:
        parsed["usage"] = usage
    if cost is not None:
        parsed["cost"] = {"total_usd": cost}
    model = message.get("model")
    if isinstance(model, str) and model:
        parsed["model"] = model
    provider = message.get("provider")
    if isinstance(provider, str) and provider:
        parsed["provider"] = provider
    return parsed


def _looks_like_omp_jsonl(events: list[dict[str, Any]]) -> bool:
    return any(event.get("type") in OMP_JSONL_EVENT_TYPES for event in events)


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


def _last_assistant_message(events: list[dict[str, Any]]) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for event in events:
        if event.get("type") != "message_end":
            continue
        message = event.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            last = message
    return last


def _text_from_message(message: dict[str, Any]) -> str:
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _usage(message: dict[str, Any]) -> dict[str, int]:
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return {}
    parsed: dict[str, int] = {}
    for source, dest in _USAGE_KEYS:
        value = usage.get(source)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            parsed[dest] = value
    return parsed


def _cost(message: dict[str, Any]) -> float | None:
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    cost = usage.get("cost")
    if not isinstance(cost, dict):
        return None
    total = cost.get("total")
    if isinstance(total, int | float) and not isinstance(total, bool):
        return float(total)
    return None


def _tool_calls(events: list[dict[str, Any]]) -> tuple[str, ...]:
    names: list[str] = []
    for event in events:
        if event.get("type") != "tool_execution_end":
            continue
        name = event.get("toolName")
        if isinstance(name, str) and name:
            names.append(name)
    return tuple(dict.fromkeys(names))
