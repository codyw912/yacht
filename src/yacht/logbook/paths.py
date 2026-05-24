from __future__ import annotations

from pathlib import Path

from yacht.domain.model import Comparison, Task, Vessel


def preflight_artifact_path(
    logbook_dir: Path,
    comparison: Comparison | str,
    vessel: Vessel | str,
) -> Path:
    return logbook_dir / "preflight" / _name(comparison) / f"{_name(vessel)}.json"


def transcript_dir(
    logbook_dir: Path,
    comparison: Comparison | str,
    vessel: Vessel | str,
) -> Path:
    return logbook_dir / "transcripts" / _name(comparison) / _name(vessel)


def runtime_trial_root(
    logbook_dir: Path,
    comparison: Comparison | str,
    vessel: Vessel | str | None = None,
) -> Path:
    root = logbook_dir / "runtime" / _name(comparison)
    if vessel is None:
        return root
    return root / _name(vessel)


def task_attempt_path(
    logbook_dir: Path,
    comparison: Comparison,
    vessel: Vessel,
    task: Task,
) -> Path:
    return (
        logbook_dir
        / "task-attempts"
        / comparison.name
        / vessel.name
        / f"{task.id}.json"
    )


def task_transcript_path(
    logbook_dir: Path,
    comparison: Comparison,
    vessel: Vessel,
    task: Task,
) -> Path:
    return transcript_dir(logbook_dir, comparison, vessel) / "tasks" / f"{task.id}.json"


def _name(value: Comparison | Vessel | str) -> str:
    if isinstance(value, str):
        return value
    return value.name
