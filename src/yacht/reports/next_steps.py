from __future__ import annotations

import shlex


def command_step(*, label: str, command: list[str], reason: str) -> dict[str, object]:
    return {
        "label": label,
        "reason": reason,
        "command": command,
        "command_preview": shlex.join(command),
    }
