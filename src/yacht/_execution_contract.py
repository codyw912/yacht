"""Shared execution-plan and evidence-summary validation.

Stdlib only so the Harbor launcher image can copy this file into
``yacht_harbor_agents.execution_contract`` without pulling in Yacht.
"""

from __future__ import annotations

import math
import re
from typing import Any

CONTROLLED_OMP_VERSION = "18.2.6"
CONTROLLED_EXECUTION_HARNESSES = frozenset({"omp"})
EXECUTION_SCHEMA = "yacht.execution.v1"
EXECUTION_MODES = frozenset({"single", "retained"})
CAPTURE_MAX_BYTES = 16 * 1024 * 1024
CAPTURE_TOTAL_MAX_BYTES = 64 * 1024 * 1024
#: Canonical grammars, shared verbatim with the public JSON Schema.
#: `(?![\s\S])` is the portable end assertion: unlike `$` it never
#: accepts a trailing newline in either Python or ECMA-262 regex.
TURN_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}(?![\s\S])"
#: A capture id is derived: stable turn id + '-' + declaration index,
#: so it is longer than a turn id and is not a turn id itself.
CAPTURE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}-(?:0|[1-9][0-9]*)(?![\s\S])"
SHA256_PATTERN = r"^[0-9a-f]{64}(?![\s\S])"
TURN_ID_RE = re.compile(TURN_ID_PATTERN)
CAPTURE_ID_RE = re.compile(CAPTURE_ID_PATTERN)
_SHA256_HEX = re.compile(SHA256_PATTERN)
_MESSAGE_ENDINGS = frozenset({"natural", "cap", "timeout", "error"})
_CAPTURE_STATUSES = frozenset({"missing", "captured", "error"})

_SINGLE_KEYS = frozenset(
    {"mode", "max_turns", "message_timeout_seconds", "timeout_seconds", "advisor"}
)
_RETAINED_KEYS = _SINGLE_KEYS | {"initial_turn_id", "turns", "captures"}
_TURN_KEYS = frozenset({"id", "instruction"})
_CAPTURE_KEYS = frozenset({"id", "after", "path", "max_bytes"})
_ADVISOR_PLAN_KEYS = frozenset({"model", "tools", "instructions"})
_SUMMARY_REQUIRED = (
    "schema",
    "mode",
    "max_turns",
    "message_timeout_seconds",
    "timeout_seconds",
    "session_ids",
    "messages",
    "captures",
    "valid",
    "model",
    "harness",
    "harness_version",
    "settings",
    "usage",
    "cost_usd",
)
_SUMMARY_KEYS = frozenset(_SUMMARY_REQUIRED) | {"error", "ended", "handoff", "advisor"}
_MESSAGE_REQUIRED = (
    "id",
    "ended",
    "loops_started",
    "loops_completed",
    "continuation_possible",
    "started_at",
    "finished_at",
)
_MESSAGE_KEYS = frozenset(_MESSAGE_REQUIRED) | {
    "usage",
    "cost_usd",
    "advisor",
}
_SUMMARY_CAPTURE_REQUIRED = ("after", "path", "status")
_SUMMARY_CAPTURE_KEYS = frozenset(_SUMMARY_CAPTURE_REQUIRED) | {
    "id",
    "bytes",
    "sha256",
    "artifact",
    "error",
}


class ExecutionContractError(ValueError):
    """Raised when an execution plan or summary does not match the contract."""


def supports_controlled_execution(harness: str, version: str) -> bool:
    return (
        harness in CONTROLLED_EXECUTION_HARNESSES and version == CONTROLLED_OMP_VERSION
    )


def validate_execution_plan(plan: object) -> None:
    if not isinstance(plan, dict):
        raise ExecutionContractError("execution plan must be an object")
    unknown = sorted(set(plan) - _RETAINED_KEYS)
    if unknown:
        raise ExecutionContractError("unknown keys: " + ", ".join(unknown))
    mode = plan.get("mode")
    if mode not in EXECUTION_MODES:
        raise ExecutionContractError("mode must be single or retained")
    for key in ("max_turns", "message_timeout_seconds", "timeout_seconds"):
        _require_positive_int(plan.get(key), key)
    if mode == "single":
        extra = sorted(set(plan) - _SINGLE_KEYS)
        if extra:
            raise ExecutionContractError(
                "single mode does not accept " + ", ".join(extra)
            )
        _validate_advisor_plan(plan.get("advisor"))
        return
    _validate_advisor_plan(plan.get("advisor"))
    _validate_retained_plan(plan)


def _validate_advisor_plan(value: object) -> None:
    """Validate the optional opt-in advisor arm (ADR 0026).

    An explicit advisor model is required: without it the advisor role falls
    back to the ``slow`` priority chain and could resolve a paid model the
    trial never intended. ``tools`` defaults to read/grep/glob driver-side; an
    explicit empty list grants the advisor no tools.
    """
    if value is None:
        return
    advisor = _require_object(value, "advisor")
    unknown = sorted(set(advisor) - _ADVISOR_PLAN_KEYS)
    if unknown:
        raise ExecutionContractError("advisor unknown keys: " + ", ".join(unknown))
    _require_non_empty_string(advisor.get("model"), "advisor.model")
    tools = advisor.get("tools")
    if tools is not None and (
        not isinstance(tools, list)
        or not all(isinstance(item, str) and item for item in tools)
    ):
        raise ExecutionContractError(
            "advisor.tools must be a list of non-empty strings"
        )
    instructions = advisor.get("instructions")
    if instructions is not None and not isinstance(instructions, str):
        raise ExecutionContractError("advisor.instructions must be a string")


def _validate_summary_advisor(value: object) -> None:
    """Validate the reported advisor block (ADR 0026).

    Advisor spend is reported per advisor, never folded into the primary's
    ``usage``/``cost_usd``. ``status`` distinguishes "advisor ran and spent X"
    from "advisor died and looks free."
    """
    block = _require_object(value, "execution summary.advisor")
    unknown = sorted(set(block) - {"enabled", "advisors", "cost_usd"})
    if unknown:
        raise ExecutionContractError(
            "execution summary.advisor unknown keys: " + ", ".join(unknown)
        )
    if not isinstance(block.get("enabled"), bool):
        raise ExecutionContractError(
            "execution summary.advisor.enabled must be a boolean"
        )
    _require_cost(block.get("cost_usd"), "execution summary.advisor.cost_usd")
    advisors = block.get("advisors")
    if not isinstance(advisors, list):
        raise ExecutionContractError(
            "execution summary.advisor.advisors must be a list"
        )
    statuses = {"running", "paused", "quota_exhausted", "error", "no_model"}
    entry_keys = {"name", "status", "model", "tokens", "cost", "messages"}
    for index, item in enumerate(advisors):
        path = f"execution summary.advisor.advisors[{index}]"
        entry = _require_object(item, path)
        unknown = sorted(set(entry) - entry_keys)
        if unknown:
            raise ExecutionContractError(f"{path} unknown keys: " + ", ".join(unknown))
        for key in ("name", "status", "tokens", "cost", "messages"):
            if key not in entry:
                raise ExecutionContractError(f"{path}.{key} is required")
        _require_non_empty_string(entry["name"], f"{path}.name")
        if entry["status"] not in statuses:
            raise ExecutionContractError(
                f"{path}.status must be one of: " + ", ".join(sorted(statuses))
            )
        if "model" in entry:
            _require_non_empty_string(entry["model"], f"{path}.model")
        _validate_numeric_map(entry["tokens"], f"{path}.tokens")
        # The cost *key* is required so a missing ledger can't read as "free",
        # but its value may be null: _normalize_advisor_report maps an unpriced
        # (subscription) advisor's synthesized 0 to None — unknown, not free.
        _require_cost(entry["cost"], f"{path}.cost")
        _validate_numeric_map(entry["messages"], f"{path}.messages")


def validate_execution_summary(summary: object) -> None:
    payload = _require_object(summary, "execution summary")
    unknown = sorted(set(payload) - _SUMMARY_KEYS)
    if unknown:
        raise ExecutionContractError(
            "execution summary unknown keys: " + ", ".join(unknown)
        )
    for key in _SUMMARY_REQUIRED:
        if key not in payload:
            raise ExecutionContractError(f"execution summary.{key} is required")
    if payload["schema"] != EXECUTION_SCHEMA:
        raise ExecutionContractError(
            f"execution summary.schema must be {EXECUTION_SCHEMA}"
        )
    if payload["mode"] not in EXECUTION_MODES:
        raise ExecutionContractError(
            "execution summary.mode must be single or retained"
        )
    for key in ("max_turns", "message_timeout_seconds", "timeout_seconds"):
        _require_positive_int(payload[key], f"execution summary.{key}")
    session_ids = payload["session_ids"]
    if not isinstance(session_ids, list) or not all(
        isinstance(item, str) and item for item in session_ids
    ):
        raise ExecutionContractError(
            "execution summary.session_ids must be a list of non-empty strings"
        )
    if not isinstance(payload["valid"], bool):
        raise ExecutionContractError("execution summary.valid must be a boolean")
    for key in ("model", "harness", "harness_version"):
        _require_non_empty_string(payload[key], f"execution summary.{key}")
    if "error" in payload:
        _require_non_empty_string(payload["error"], "execution summary.error")
    if "ended" in payload and payload["ended"] not in _MESSAGE_ENDINGS:
        raise ExecutionContractError(
            "execution summary.ended must be one of: "
            + ", ".join(sorted(_MESSAGE_ENDINGS))
        )
    if "handoff" in payload:
        _validate_summary_handoff(payload["handoff"])
    if "advisor" in payload:
        _validate_summary_advisor(payload["advisor"])
    _validate_summary_settings(payload["settings"])
    _validate_numeric_map(payload["usage"], "execution summary.usage")
    _require_cost(payload["cost_usd"], "execution summary.cost_usd")
    messages = payload["messages"]
    if not isinstance(messages, list):
        raise ExecutionContractError("execution summary.messages must be a list")
    if messages and not session_ids:
        raise ExecutionContractError(
            "execution summary.session_ids must be non-empty when messages exist"
        )
    delivered: set[str] = set()
    max_turns = payload["max_turns"]
    for index, item in enumerate(messages):
        message_id = _validate_summary_message(
            item,
            f"execution summary.messages[{index}]",
            max_turns=max_turns,
        )
        delivered.add(message_id)
    captures = payload["captures"]
    if not isinstance(captures, list):
        raise ExecutionContractError("execution summary.captures must be a list")
    for index, item in enumerate(captures):
        _validate_summary_capture(
            item,
            f"execution summary.captures[{index}]",
            delivered=delivered,
        )


def _validate_retained_plan(plan: dict[str, Any]) -> None:
    initial = plan.get("initial_turn_id")
    _require_turn_id(initial, "initial_turn_id")
    turns = plan.get("turns")
    if not isinstance(turns, list):
        raise ExecutionContractError("turns must be a list")
    seen = {initial}
    for index, item in enumerate(turns):
        path = f"turns[{index}]"
        turn = _require_object(item, path)
        unknown = sorted(set(turn) - _TURN_KEYS)
        if unknown:
            raise ExecutionContractError(f"{path} unknown keys: {', '.join(unknown)}")
        for key in _TURN_KEYS:
            if key not in turn:
                raise ExecutionContractError(f"{path}.{key} is required")
        turn_id = turn["id"]
        _require_turn_id(turn_id, f"{path}.id")
        if turn_id in seen:
            raise ExecutionContractError(f"{path}.id {turn_id!r} is not unique")
        seen.add(turn_id)
        instruction = turn["instruction"]
        if not isinstance(instruction, str) or not instruction.strip():
            raise ExecutionContractError(
                f"{path}.instruction must be a non-empty string"
            )
    captures = plan.get("captures")
    if not isinstance(captures, list):
        raise ExecutionContractError("captures must be a list")
    pairs: set[tuple[str, str]] = set()
    total = 0
    for index, item in enumerate(captures):
        path = f"captures[{index}]"
        capture = _require_object(item, path)
        unknown = sorted(set(capture) - _CAPTURE_KEYS)
        if unknown:
            raise ExecutionContractError(f"{path} unknown keys: {', '.join(unknown)}")
        for key in _CAPTURE_KEYS:
            if key not in capture:
                raise ExecutionContractError(f"{path}.{key} is required")
        after = _require_turn_id(capture["after"], f"{path}.after")
        if after not in seen:
            raise ExecutionContractError(
                f"{path}.after {after!r} does not name a known turn"
            )
        rel_path = _require_relative_posix_path(capture["path"], f"{path}.path")
        pair = (after, rel_path)
        if pair in pairs:
            raise ExecutionContractError(
                f"{path} duplicates after {after!r} path {rel_path!r}"
            )
        pairs.add(pair)
        max_bytes = capture["max_bytes"]
        _require_positive_int(max_bytes, f"{path}.max_bytes")
        if max_bytes > CAPTURE_MAX_BYTES:
            raise ExecutionContractError(
                f"{path}.max_bytes must be <= {CAPTURE_MAX_BYTES}"
            )
        expected_id = f"{after}-{index}"
        capture_id = capture["id"]
        if not isinstance(capture_id, str) or not capture_id:
            raise ExecutionContractError(f"{path}.id must be a non-empty string")
        if capture_id != expected_id:
            raise ExecutionContractError(f"{path}.id must be {expected_id!r}")
        total += max_bytes
    if total > CAPTURE_TOTAL_MAX_BYTES:
        raise ExecutionContractError(
            f"capture max_bytes total must be <= {CAPTURE_TOTAL_MAX_BYTES}"
        )


def _validate_summary_settings(value: object) -> None:
    settings = _require_object(value, "execution summary.settings")
    for key, item in settings.items():
        if not isinstance(key, str) or not key:
            raise ExecutionContractError(
                "execution summary.settings keys must be non-empty strings"
            )
        _validate_setting_value(item, f"execution summary.settings.{key}")


def _validate_setting_value(value: object, path: str) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, str) and value:
        return
    if isinstance(value, list) and all(
        isinstance(item, str) and item for item in value
    ):
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ExecutionContractError(f"{path} keys must be non-empty strings")
            _validate_setting_value(item, f"{path}.{key}")
        return
    raise ExecutionContractError(
        f"{path} must be a boolean, non-empty string, list of strings, or object"
    )


def _validate_summary_handoff(value: object) -> None:
    handoff = _require_object(value, "execution summary.handoff")
    if not handoff:
        raise ExecutionContractError("execution summary.handoff must not be empty")
    for key, item in handoff.items():
        if not isinstance(key, str) or not key:
            raise ExecutionContractError(
                "execution summary.handoff keys must be non-empty strings"
            )
        _require_non_empty_string(item, f"execution summary.handoff.{key}")


def _validate_summary_message(value: object, path: str, *, max_turns: int) -> str:
    item = _require_object(value, path)
    unknown = sorted(set(item) - _MESSAGE_KEYS)
    if unknown:
        raise ExecutionContractError(f"{path} unknown keys: {', '.join(unknown)}")
    for key in _MESSAGE_REQUIRED:
        if key not in item:
            raise ExecutionContractError(f"{path}.{key} is required")
    message_id = _require_turn_id(item["id"], f"{path}.id")
    ended = item["ended"]
    if ended not in _MESSAGE_ENDINGS:
        raise ExecutionContractError(
            f"{path}.ended must be one of: {', '.join(sorted(_MESSAGE_ENDINGS))}"
        )
    started = _require_non_negative_int(item["loops_started"], f"{path}.loops_started")
    completed = _require_non_negative_int(
        item["loops_completed"], f"{path}.loops_completed"
    )
    if completed > started:
        raise ExecutionContractError(f"{path}.loops_completed must be <= loops_started")
    if started > max_turns:
        raise ExecutionContractError(f"{path}.loops_started must be <= max_turns")
    if not isinstance(item["continuation_possible"], bool):
        raise ExecutionContractError(f"{path}.continuation_possible must be a boolean")
    _require_non_empty_string(item["started_at"], f"{path}.started_at")
    _require_non_empty_string(item["finished_at"], f"{path}.finished_at")
    if "usage" in item:
        _validate_numeric_map(item["usage"], f"{path}.usage")
    if "cost_usd" in item:
        _require_cost(item["cost_usd"], f"{path}.cost_usd")
    return message_id


def _validate_summary_capture(value: object, path: str, *, delivered: set[str]) -> None:
    item = _require_object(value, path)
    unknown = sorted(set(item) - _SUMMARY_CAPTURE_KEYS)
    if unknown:
        raise ExecutionContractError(f"{path} unknown keys: {', '.join(unknown)}")
    for key in _SUMMARY_CAPTURE_REQUIRED:
        if key not in item:
            raise ExecutionContractError(f"{path}.{key} is required")
    if "id" in item:
        _require_capture_id(item["id"], f"{path}.id")
    after = _require_turn_id(item["after"], f"{path}.after")
    if after not in delivered:
        raise ExecutionContractError(
            f"{path}.after {after!r} does not name a delivered message"
        )
    _require_relative_posix_path(item["path"], f"{path}.path")
    status = item["status"]
    if status not in _CAPTURE_STATUSES:
        raise ExecutionContractError(
            f"{path}.status must be one of: {', '.join(sorted(_CAPTURE_STATUSES))}"
        )
    if status == "captured":
        _require_non_negative_int(item.get("bytes"), f"{path}.bytes")
        sha256 = item.get("sha256")
        if not isinstance(sha256, str) or _SHA256_HEX.fullmatch(sha256) is None:
            raise ExecutionContractError(f"{path}.sha256 must be a 64-char hex digest")
        _require_non_empty_string(item.get("artifact"), f"{path}.artifact")
    if status == "error":
        _require_non_empty_string(item.get("error"), f"{path}.error")


def _require_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionContractError(f"{path} must be an object")
    return value


def _require_positive_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ExecutionContractError(f"{path} must be an integer >= 1")
    return value


def _require_non_negative_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExecutionContractError(f"{path} must be an integer >= 0")
    return value


def _require_non_empty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExecutionContractError(f"{path} must be a non-empty string")
    return value


def _require_turn_id(value: object, path: str) -> str:
    if not isinstance(value, str) or TURN_ID_RE.match(value) is None:
        raise ExecutionContractError(
            f"{path} must match [A-Za-z0-9][A-Za-z0-9_-]{{0,63}}"
        )
    return value


def _require_capture_id(value: object, path: str) -> str:
    if not isinstance(value, str) or CAPTURE_ID_RE.match(value) is None:
        raise ExecutionContractError(
            f"{path} must be a turn id followed by '-' and the declaration index"
        )
    return value


def _require_relative_posix_path(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExecutionContractError(f"{path} must be a relative POSIX path")
    if value.startswith("/") or "\\" in value or "\0" in value:
        raise ExecutionContractError(f"{path} must be a relative POSIX path")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ExecutionContractError(
            f"{path} must not contain empty, '.', or '..' components"
        )
    return value


def _require_cost(value: object, path: str) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ExecutionContractError(f"{path} must be a finite number >= 0 or null")


def _validate_numeric_map(value: object, path: str) -> None:
    payload = _require_object(value, path)
    for key, item in payload.items():
        if not isinstance(key, str) or not key:
            raise ExecutionContractError(f"{path} keys must be non-empty strings")
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            or item < 0
        ):
            raise ExecutionContractError(f"{path}.{key} must be a finite number >= 0")
