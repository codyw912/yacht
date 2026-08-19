from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from yacht.logbook.index import LogbookSnapshot, LogbookState


def load_logbook_surfaces(logbook_dir: Path) -> dict[str, Any] | None:
    for path in (
        logbook_dir / "real-benchmark-eval.json",
        logbook_dir / "real-benchmark-repetitions.json",
    ):
        surfaces = _load_surfaces(path)
        if surfaces is not None:
            return surfaces
    return None


def load_snapshot_surfaces(snapshot: LogbookSnapshot) -> dict[str, Any] | None:
    if snapshot.state is LogbookState.LEGACY_SCORECARD_ONLY:
        return load_logbook_surfaces(snapshot.logbook)
    for name in ("real_benchmark_eval", "real_benchmark_repetitions"):
        artifact = snapshot.artifact(name)
        if artifact is not None and artifact.file_present:
            surfaces = _load_surfaces(artifact.path)
            if surfaces is not None:
                return surfaces
    return None


def format_surface_summary(surfaces: dict[str, Any] | None) -> str | None:
    if surfaces is None:
        return None
    parts = [
        f"agents={_list_value(surfaces.get('agent_harnesses'))}",
        f"tools={_list_value(surfaces.get('tools'))}",
    ]
    benchmark = surfaces.get("benchmark")
    if isinstance(benchmark, dict):
        parts.append(f"benchmark={_benchmark_value(benchmark)}")
    return " | ".join(parts)


def _load_surfaces(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    surfaces = payload.get("surfaces")
    if isinstance(surfaces, dict):
        return surfaces
    agent = payload.get("agent")
    if isinstance(agent, str) and agent:
        return {"agent_harnesses": [agent]}
    return None


def _list_value(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    return ",".join(str(item) for item in value)


def _benchmark_value(benchmark: dict[str, Any]) -> str:
    parts = [
        str(benchmark.get("adapter", "unknown")),
        str(benchmark.get("dataset", "unknown")),
        str(benchmark.get("split", "unknown")),
        str(benchmark.get("execution_harness", "unknown")),
    ]
    return "/".join(parts)
