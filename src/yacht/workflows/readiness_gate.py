from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yacht.reports.benchmark_readiness import render_benchmark_readiness_report


@dataclass(frozen=True)
class ReadinessGateResult:
    summary_json: str
    summary: dict[str, Any]
    blocked_vessel_count: int
    exit_code: int


def evaluate_readiness_gate(logbook_dir: Path) -> ReadinessGateResult:
    summary_json = render_benchmark_readiness_report(logbook_dir, "summary-json")
    summary = json.loads(summary_json)
    blocked_vessel_count = summary["blocked_vessel_count"]
    return ReadinessGateResult(
        summary_json=summary_json,
        summary=summary,
        blocked_vessel_count=blocked_vessel_count,
        exit_code=1 if blocked_vessel_count else 0,
    )
