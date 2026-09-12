"""Execution-plan rendering for bounded OMP trials.

A task opts into controlled execution with an [execution] table in
task.toml. The plan is normalized host-side at job-render time and
embedded in the terminal-bench job so render-time validation and
runtime behavior cannot drift. Validation lives in the shared
stdlib contract so the Harbor launcher can copy the same source.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from yacht._execution_contract import (
    ExecutionContractError,
    validate_execution_plan,
)
from yacht.domain.model import ConfigError

_ALLOWED_KEYS = {
    "mode",
    "max_turns",
    "message_timeout_seconds",
    "timeout_seconds",
    "initial_turn_id",
    "turns",
    "captures",
}
_TURN_KEYS = {"id", "instruction"}
_CAPTURE_KEYS = {"after", "path", "max_bytes"}


def render_execution_plan(task_dir: Path) -> dict[str, Any] | None:
    """The task's resolved execution plan, or None when not opted in.

    Raises ConfigError on any invalid declaration; validation runs
    host-side before any container starts.
    """
    config_path = task_dir / "task.toml"
    if not config_path.is_file():
        raise ConfigError(f"task directory {task_dir} is missing task.toml")
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{config_path} is not valid TOML: {error}") from error
    if "execution" in payload and "episodes" in payload:
        raise ConfigError(f"{config_path} [execution] conflicts with [episodes]")
    table = payload.get("execution")
    if table is None:
        return None
    if not isinstance(table, dict):
        raise ConfigError(f"{config_path} [execution] must be a table")
    unknown = sorted(set(table) - _ALLOWED_KEYS)
    if unknown:
        raise ConfigError(
            f"{config_path} [execution] has unknown keys: {', '.join(unknown)}"
        )
    try:
        plan = _normalize_execution_table(table)
        validate_execution_plan(plan)
    except ExecutionContractError as error:
        raise ConfigError(f"{task_dir} [execution] {error}") from error
    return plan


def _normalize_execution_table(table: dict[str, Any]) -> dict[str, Any]:
    mode = table.get("mode")
    plan: dict[str, Any] = {
        "mode": mode,
        "max_turns": table.get("max_turns"),
        "message_timeout_seconds": table.get("message_timeout_seconds"),
        "timeout_seconds": table.get("timeout_seconds"),
    }
    if mode == "retained":
        plan["initial_turn_id"] = table.get("initial_turn_id", "initial")
        plan["turns"] = _normalize_turns(table.get("turns", []))
        plan["captures"] = _normalize_captures(table.get("captures", []))
    elif mode == "single":
        extra = [
            key for key in ("initial_turn_id", "turns", "captures") if key in table
        ]
        if extra:
            raise ExecutionContractError(
                "single mode does not accept " + ", ".join(extra)
            )
    return plan


def _normalize_turns(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ExecutionContractError("turns must be a list")
    turns: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        path = f"turns[{index}]"
        if not isinstance(item, dict):
            raise ExecutionContractError(f"{path} must be a table")
        unknown = sorted(set(item) - _TURN_KEYS)
        if unknown:
            raise ExecutionContractError(f"{path} unknown keys: {', '.join(unknown)}")
        turns.append(
            {
                "id": item.get("id"),
                "instruction": item.get("instruction"),
            }
        )
    return turns


def _normalize_captures(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ExecutionContractError("captures must be a list")
    captures: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        path = f"captures[{index}]"
        if not isinstance(item, dict):
            raise ExecutionContractError(f"{path} must be a table")
        unknown = sorted(set(item) - _CAPTURE_KEYS)
        if unknown:
            raise ExecutionContractError(f"{path} unknown keys: {', '.join(unknown)}")
        after = item.get("after")
        captures.append(
            {
                "id": f"{after}-{index}",
                "after": after,
                "path": item.get("path"),
                "max_bytes": item.get("max_bytes"),
            }
        )
    return captures
