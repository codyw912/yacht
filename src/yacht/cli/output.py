from __future__ import annotations

import json
import sys
from pathlib import Path


def print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2))


def stderr_progress(message: str) -> None:
    print(f"yacht: {message}", file=sys.stderr, flush=True)


def emit_report(report: str, output: Path | None) -> int:
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        return 0
    print(report, end="")
    return 0
