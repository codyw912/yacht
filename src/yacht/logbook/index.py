from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from yacht.contracts.schemas import (
    RUN_INDEX_V2_SCHEMA,
    SchemaValidationError,
    validate_run_index_document,
)
from yacht.domain.model import ConfigError
from yacht.logbook.io import load_json_object, write_json_atomic


RUN_INDEX_PATH = Path("run-index.json")

_LEGACY_ARTIFACT_PATHS = {
    "course_handoff": Path("course-handoff.json"),
    "benchmark_scorecard": Path("benchmark-scorecard.json"),
    "task_attempt_scorecard": Path("task-attempt-scorecard.json"),
    "scorecard": Path("scorecard.json"),
    "smoke_readiness_report": Path("smoke-readiness-report.json"),
    "benchmark_aggregate": Path("benchmark-aggregate.json"),
    "real_benchmark_repetitions": Path("real-benchmark-repetitions.json"),
    "benchmark_grading_collection": Path("benchmark-grading-collection.json"),
    "benchmark_launch_result": Path("benchmark-launch-result.json"),
    "real_benchmark_eval": Path("real-benchmark-eval.json"),
    "real_smoke_runbook": Path("real-smoke-runbook.json"),
    "smoke_report": Path("smoke-report.txt"),
}


class LogbookState(StrEnum):
    CURRENT_INDEXED = "current-indexed"
    HISTORICAL_V1 = "historical-v1"
    LEGACY_SCORECARD_ONLY = "legacy-scorecard-only"
    BROKEN = "broken"


@dataclass(frozen=True)
class ComparisonReference:
    name: str
    course: str
    vessels: tuple[str, ...]


@dataclass(frozen=True)
class ArtifactReference:
    name: str
    path: Path
    recorded_present: bool

    @property
    def present(self) -> bool:
        try:
            return self.path.exists()
        except OSError:
            return False

    @property
    def file_present(self) -> bool:
        return _is_file(self.path)


@dataclass(frozen=True)
class ChildLogbookReference:
    path: Path
    recorded_status: str

    @property
    def present(self) -> bool:
        try:
            return self.path.is_dir()
        except OSError:
            return False


@dataclass(frozen=True)
class LogbookSnapshot:
    logbook: Path
    state: LogbookState
    schema: str | None = None
    run_kind: str | None = None
    status: str | None = None
    stage: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    terminal_at: str | None = None
    config_path: str | None = None
    regatta: str | None = None
    course: str | None = None
    comparisons: tuple[ComparisonReference, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    children: tuple[ChildLogbookReference, ...] = ()
    error: str | None = None

    def artifact(self, name: str) -> ArtifactReference | None:
        return next(
            (artifact for artifact in self.artifacts if artifact.name == name),
            None,
        )


class RunIndexLifecycle:
    def __init__(
        self,
        *,
        logbook_dir: Path,
        config_path: Path,
        run_kind: str,
        regatta: str,
        course: str,
        comparisons: Sequence[Any],
        artifacts: Mapping[str, str | Path],
    ) -> None:
        self._logbook_dir = logbook_dir
        self._artifact_paths = {
            name: _relative_artifact_path(logbook_dir, path)
            for name, path in artifacts.items()
        }
        timestamp = _timestamp()
        self._document: dict[str, Any] = {
            "schema": RUN_INDEX_V2_SCHEMA,
            "run_kind": run_kind,
            "status": "running",
            "stage": "starting",
            "started_at": timestamp,
            "updated_at": timestamp,
            "config_path": str(config_path),
            "regatta": regatta,
            "course": course,
            "comparisons": [
                _comparison_to_json(comparison) for comparison in comparisons
            ],
            "artifacts": {},
        }
        self._persist()

    @property
    def stage(self) -> str:
        return str(self._document["stage"])

    def advance(self, stage: str) -> None:
        if self._document["status"] != "running":
            raise ConfigError("cannot advance a terminal run index")
        self._persist(stage=stage, updated_at=_timestamp())

    def finish(self, status: str, *, stage: str | None = None) -> None:
        if self._document["status"] != "running":
            raise ConfigError("cannot finish a terminal run index")
        if status not in {"complete", "blocked", "failed"}:
            raise ConfigError(f"invalid terminal run-index status: {status}")
        timestamp = _timestamp()
        updates: dict[str, object] = {
            "status": status,
            "updated_at": timestamp,
            "terminal_at": timestamp,
        }
        if stage is not None:
            updates["stage"] = stage
        self._persist(**updates)

    def record_failure(self, error: BaseException) -> None:
        if self._document["status"] != "running":
            return
        try:
            self.finish("failed")
        except BaseException as index_error:
            error.add_note(f"could not record run-index failure: {index_error}")

    def _persist(self, **updates: object) -> None:
        document = {**self._document, **updates}
        document["artifacts"] = {
            name: {
                "path": path.as_posix(),
                "present": _artifact_present(self._logbook_dir / path),
            }
            for name, path in self._artifact_paths.items()
        }
        validate_run_index_document(document)
        write_json_atomic(self._logbook_dir / RUN_INDEX_PATH, document)
        self._document = document


def start_run_index(
    *,
    logbook_dir: Path,
    config_path: Path,
    run_kind: str,
    regatta: str,
    course: str,
    comparisons: Sequence[Any],
    artifacts: Mapping[str, str | Path],
) -> RunIndexLifecycle:
    return RunIndexLifecycle(
        logbook_dir=logbook_dir,
        config_path=config_path,
        run_kind=run_kind,
        regatta=regatta,
        course=course,
        comparisons=comparisons,
        artifacts=artifacts,
    )


def is_logbook_candidate(logbook_dir: Path) -> bool:
    index_path = logbook_dir / RUN_INDEX_PATH
    try:
        if index_path.exists() or index_path.is_symlink():
            return True
    except OSError:
        return False
    return any(_is_file(logbook_dir / path) for path in _LEGACY_ARTIFACT_PATHS.values())


def read_logbook(logbook_dir: Path) -> LogbookSnapshot:
    """Read one Logbook without interpreting its Scorecard contents."""
    if not logbook_dir.is_dir():
        return _broken_logbook(
            logbook_dir,
            f"logbook directory not found: {logbook_dir}",
        )

    index_path = logbook_dir / RUN_INDEX_PATH
    if index_path.exists() or index_path.is_symlink():
        try:
            root = logbook_dir.resolve()
            resolved_index = index_path.resolve()
            if not resolved_index.is_relative_to(root):
                raise ConfigError("run index artifact escapes the Logbook")
            document = load_json_object(index_path, "run index artifact")
            validate_run_index_document(document)
            return _indexed_logbook(logbook_dir, document)
        except (ConfigError, OSError, SchemaValidationError) as error:
            return _broken_logbook(
                logbook_dir,
                f"run index artifact {index_path}: {error}",
            )

    try:
        return _legacy_logbook(logbook_dir)
    except (ConfigError, OSError) as error:
        return _broken_logbook(
            logbook_dir,
            f"could not inspect legacy Logbook {logbook_dir}: {error}",
        )


def require_logbook(logbook_dir: Path) -> LogbookSnapshot:
    snapshot = read_logbook(logbook_dir)
    if snapshot.state is LogbookState.BROKEN:
        raise ConfigError(snapshot.error or f"broken Logbook: {logbook_dir}")
    return snapshot


def _indexed_logbook(
    logbook_dir: Path,
    document: dict[str, Any],
) -> LogbookSnapshot:
    schema_name = str(document["schema"])
    state = (
        LogbookState.CURRENT_INDEXED
        if schema_name == RUN_INDEX_V2_SCHEMA
        else LogbookState.HISTORICAL_V1
    )
    recorded_root = (
        str(document["logbook"]) if state is LogbookState.HISTORICAL_V1 else None
    )
    artifacts = tuple(
        ArtifactReference(
            name=str(name),
            path=_resolve_index_reference(
                logbook_dir,
                str(value["path"]),
                recorded_root=recorded_root,
            ),
            recorded_present=bool(value["present"]),
        )
        for name, value in document["artifacts"].items()
    )
    children = tuple(
        ChildLogbookReference(
            path=_resolve_index_reference(
                logbook_dir,
                str(child["path"]),
                recorded_root=None,
            ),
            recorded_status=str(child["status"]),
        )
        for child in document.get("children", ())
    )
    return LogbookSnapshot(
        logbook=logbook_dir,
        state=state,
        schema=schema_name,
        run_kind=str(document["run_kind"]),
        status=str(document["status"]),
        stage=_optional_string(document.get("stage")),
        started_at=_optional_string(document.get("started_at")),
        updated_at=str(document["updated_at"]),
        terminal_at=_optional_string(document.get("terminal_at")),
        config_path=str(document["config_path"]),
        regatta=str(document["regatta"]),
        course=str(document["course"]),
        comparisons=tuple(
            ComparisonReference(
                name=str(comparison["name"]),
                course=str(comparison["course"]),
                vessels=tuple(str(vessel) for vessel in comparison["vessels"]),
            )
            for comparison in document["comparisons"]
        ),
        artifacts=artifacts,
        children=children,
    )


def _resolve_index_reference(
    logbook_dir: Path,
    value: str,
    *,
    recorded_root: str | None,
) -> Path:
    if recorded_root is not None:
        reference = _normalize_v1_reference(value, recorded_root)
    else:
        reference = Path(value)
        if "\\" in value:
            raise ConfigError(f"index reference must use forward slashes: {value!r}")
        if reference.is_absolute():
            raise ConfigError(f"index reference must be relative: {value!r}")

    if reference == Path(".") or ".." in reference.parts:
        raise ConfigError(f"index reference escapes the Logbook: {value!r}")

    root = logbook_dir.resolve()
    resolved = (root / reference).resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ConfigError(f"index reference escapes the Logbook: {value!r}")
    return resolved


def _normalize_v1_reference(value: str, recorded_root: str) -> Path:
    windows_path = (
        "\\" in value
        or "\\" in recorded_root
        or bool(PureWindowsPath(value).drive)
        or bool(PureWindowsPath(recorded_root).drive)
    )
    path_type = PureWindowsPath if windows_path else PurePosixPath
    reference = path_type(value)
    root = path_type(recorded_root)
    if reference.is_absolute():
        if not root.is_absolute() or not reference.is_relative_to(root):
            raise ConfigError(
                f"historical index reference is outside its Logbook: {value}"
            )
        relative = reference.relative_to(root)
    elif not root.is_absolute() and reference.is_relative_to(root):
        relative = reference.relative_to(root)
    else:
        relative = reference
    return Path(*relative.parts)


def _legacy_logbook(logbook_dir: Path) -> LogbookSnapshot:
    artifacts = tuple(
        ArtifactReference(
            name=name,
            path=_resolve_index_reference(
                logbook_dir,
                relative_path.as_posix(),
                recorded_root=None,
            ),
            recorded_present=True,
        )
        for name, relative_path in _LEGACY_ARTIFACT_PATHS.items()
        if (logbook_dir / relative_path).is_file()
    )
    if not artifacts:
        return _broken_logbook(
            logbook_dir,
            "no run index or legacy Scorecard artifacts found",
        )
    smoke = any(
        artifact.name == "smoke_readiness_report" for artifact in artifacts
    ) and all(artifact.name != "benchmark_scorecard" for artifact in artifacts)
    updated_timestamp = max(artifact.path.stat().st_mtime for artifact in artifacts)
    return LogbookSnapshot(
        logbook=logbook_dir,
        state=LogbookState.LEGACY_SCORECARD_ONLY,
        run_kind="real-smoke" if smoke else "real-benchmark",
        status="unknown",
        updated_at=datetime.fromtimestamp(updated_timestamp, UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        artifacts=artifacts,
    )


def _broken_logbook(logbook_dir: Path, error: str) -> LogbookSnapshot:
    return LogbookSnapshot(
        logbook=logbook_dir,
        state=LogbookState.BROKEN,
        error=error,
    )


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _comparison_to_json(comparison: Any) -> dict[str, Any]:
    if not isinstance(comparison, Mapping):
        return {
            "name": str(comparison.name),
            "course": str(comparison.course),
            "vessels": [str(vessel) for vessel in comparison.vessels],
        }
    return {
        "name": str(comparison["name"]),
        "course": str(comparison["course"]),
        "vessels": [str(vessel) for vessel in comparison["vessels"]],
    }


def _relative_artifact_path(logbook_dir: Path, value: str | Path) -> Path:
    raw_path = Path(value)
    if "\\" in str(value) or ".." in raw_path.parts:
        raise ConfigError(f"artifact path escapes the Logbook: {value}")
    root = logbook_dir.resolve()
    resolved = (
        raw_path.resolve() if raw_path.is_absolute() else (root / raw_path).resolve()
    )
    if not resolved.is_relative_to(root) or resolved == root:
        raise ConfigError(f"artifact path escapes the Logbook: {value}")
    return resolved.relative_to(root)


def _artifact_present(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
