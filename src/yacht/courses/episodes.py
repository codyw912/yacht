"""Episode-plan rendering for episodic trials (ADR 0025).

A task opts into episodic execution with an [episodes] table in its
task.toml plus optional per-episode delta files episodes/00k.md. The
plan is rendered and validated host-side at job-render time and
embedded in the terminal-bench job, so render-time validation and
runtime behavior cannot drift.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError


DEFAULT_CONTINUE_INSTRUCTION = "Continue work on the project."

_ALLOWED_KEYS = {
    "max",
    "verify_between",
    "continue_instruction",
    "max_turns",
    "timeout_seconds",
}
_DELTA_NAME = re.compile(r"^(\d{3})\.md$")


def render_episode_plan(task_dir: Path) -> dict[str, Any] | None:
    """The task's resolved episode plan, or None for a single-shot task.

    Raises ConfigError on any invalid declaration; validation runs
    host-side before any container starts.
    """
    table = _episodes_table(task_dir)
    deltas = _delta_texts(task_dir)
    if table is None:
        if deltas:
            raise ConfigError(
                f"{task_dir} has episodes/ delta files but no [episodes] "
                "table in task.toml"
            )
        return None
    maximum = _positive_int(table, "max", task_dir, required=True)
    if maximum == 1:
        if deltas:
            raise ConfigError(
                f"{task_dir} [episodes] max = 1 cannot carry episodes/ deltas"
            )
        return None
    _require_contiguous(deltas, maximum, task_dir)
    verify_between = table.get("verify_between", False)
    if not isinstance(verify_between, bool):
        raise ConfigError(f"{task_dir} [episodes] verify_between must be a boolean")
    if verify_between and not (task_dir / "tests" / "test.sh").is_file():
        raise ConfigError(
            f"{task_dir} [episodes] verify_between requires tests/test.sh "
            "(the inter-episode verifier mirrors the harbor test script)"
        )
    continue_instruction = table.get(
        "continue_instruction", DEFAULT_CONTINUE_INSTRUCTION
    )
    if not isinstance(continue_instruction, str) or not continue_instruction.strip():
        raise ConfigError(
            f"{task_dir} [episodes] continue_instruction must be a non-empty string"
        )
    plan: dict[str, Any] = {
        "max": maximum,
        "verify_between": verify_between,
        "instructions": [
            deltas.get(index, continue_instruction) for index in range(2, maximum + 1)
        ],
    }
    for key in ("max_turns", "timeout_seconds"):
        value = _positive_int(table, key, task_dir, required=False)
        if value is not None:
            plan[key] = value
    return plan


def _episodes_table(task_dir: Path) -> dict[str, Any] | None:
    config_path = task_dir / "task.toml"
    if not config_path.is_file():
        raise ConfigError(f"task directory {task_dir} is missing task.toml")
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{config_path} is not valid TOML: {error}") from error
    table = payload.get("episodes")
    if table is None:
        return None
    if not isinstance(table, dict):
        raise ConfigError(f"{config_path} [episodes] must be a table")
    unknown = sorted(set(table) - _ALLOWED_KEYS)
    if unknown:
        raise ConfigError(
            f"{config_path} [episodes] has unknown keys: {', '.join(unknown)}"
        )
    return table


def _delta_texts(task_dir: Path) -> dict[int, str]:
    episodes_dir = task_dir / "episodes"
    if not episodes_dir.is_dir():
        return {}
    deltas: dict[int, str] = {}
    for item in sorted(episodes_dir.iterdir()):
        match = _DELTA_NAME.match(item.name)
        if match is None or not item.is_file():
            raise ConfigError(
                f"{episodes_dir} entry {item.name} must be a delta file "
                "named 00k.md (three digits, episode number >= 002)"
            )
        index = int(match.group(1))
        if index < 2:
            raise ConfigError(
                f"{episodes_dir}/{item.name}: episode 1 uses instruction.md; "
                "delta numbering starts at 002"
            )
        text = item.read_text(encoding="utf-8")
        if not text.strip():
            raise ConfigError(f"{episodes_dir}/{item.name} must not be empty")
        deltas[index] = text
    return deltas


def _require_contiguous(deltas: dict[int, str], maximum: int, task_dir: Path) -> None:
    if not deltas:
        return
    top = max(deltas)
    if top > maximum:
        raise ConfigError(
            f"{task_dir} episodes/{top:03d}.md exceeds [episodes] max = {maximum}"
        )
    for index in range(2, top + 1):
        if index not in deltas:
            raise ConfigError(
                f"{task_dir} episodes/ is missing {index:03d}.md; delta files "
                "must be contiguous from 002"
            )


def _positive_int(
    table: dict[str, Any], key: str, task_dir: Path, *, required: bool
) -> int | None:
    value = table.get(key)
    if value is None:
        if required:
            raise ConfigError(f"{task_dir} [episodes] must set {key}")
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{task_dir} [episodes] {key} must be an integer >= 1")
    return value
