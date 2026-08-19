from __future__ import annotations

import shlex
from pathlib import Path


def command_step(*, label: str, command: list[str], reason: str) -> dict[str, object]:
    return {
        "label": label,
        "reason": reason,
        "command": command,
        "command_preview": shlex.join(command),
    }


def relocate_command_steps(
    steps: object,
    logbook_dir: Path,
) -> list[dict[str, object]]:
    if not isinstance(steps, list):
        return []
    relocated: list[dict[str, object]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        command = step.get("command")
        label = step.get("label")
        reason = step.get("reason")
        if (
            not isinstance(command, list)
            or not all(isinstance(part, str) for part in command)
            or not isinstance(label, str)
            or not isinstance(reason, str)
        ):
            continue
        old_logbooks = {
            command[index + 1]
            for index, part in enumerate(command[:-1])
            if part == "--logbook"
            and "<" not in command[index + 1]
            and ">" not in command[index + 1]
        }
        current = str(logbook_dir)
        relocated_command = [
            _relocate_command_path(part, old_logbooks, current) for part in command
        ]
        relocated.append(
            command_step(
                label=label,
                reason=reason,
                command=relocated_command,
            )
        )
    return relocated


def _relocate_command_path(
    value: str,
    old_logbooks: set[str],
    current: str,
) -> str:
    for old in old_logbooks:
        if value == old:
            return current
        if value.startswith(f"{old}/"):
            return f"{current}{value[len(old) :]}"
    return value
