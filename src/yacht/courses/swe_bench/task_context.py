from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from yacht.domain.model import ConfigError, CourseAdapter, Task


def task_with_swe_bench_context(
    *,
    task: Task,
    adapter: CourseAdapter,
) -> Task:
    if _has_context(task):
        return task

    record = _load_swe_bench_record(adapter, task.id)
    return replace(
        task,
        repo=str(record["repo"]),
        repo_url=_repo_url(str(record["repo"])),
        base_commit=str(record["base_commit"]),
        problem_statement=str(record["problem_statement"]),
    )


def materialize_swe_bench_workspace(
    *,
    task: Task,
    workspace_root: Path,
    comparison_name: str,
    vessel_name: str,
) -> Path:
    if not _has_context(task) or task.repo_url is None or task.base_commit is None:
        raise ConfigError(
            f"SWE-bench task {task.id} is missing repo, base_commit, or "
            "problem_statement"
        )

    workspace_path = workspace_root / comparison_name / vessel_name / task.id
    if (workspace_path / ".git").is_dir():
        _git(workspace_path, "fetch", "--all", "--tags")
    else:
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        _git(
            workspace_path.parent,
            "clone",
            "--no-single-branch",
            task.repo_url,
            workspace_path.name,
        )
    _git(workspace_path, "checkout", "--force", task.base_commit)
    _git(workspace_path, "clean", "-fdx")
    return workspace_path


def _has_context(task: Task) -> bool:
    return (
        task.repo is not None
        and task.repo_url is not None
        and task.base_commit is not None
        and task.problem_statement is not None
    )


_RECORD_INDEX_CACHE: dict[tuple[str, str], dict[str, dict[str, object]]] = {}


def clear_swe_bench_record_cache() -> None:
    _RECORD_INDEX_CACHE.clear()


def _load_swe_bench_record(
    adapter: CourseAdapter,
    instance_id: str,
) -> dict[str, object]:
    dataset = _context_dataset_name(adapter.dataset)
    index = _swe_bench_record_index(dataset, adapter.split)
    record = index.get(instance_id)
    if record is None:
        raise ConfigError(
            f"SWE-bench instance {instance_id} not found in {dataset} split "
            f"{adapter.split}"
        )
    return dict(record)


def _swe_bench_record_index(
    dataset: str,
    split: str,
) -> dict[str, dict[str, object]]:
    key = (dataset, split)
    index = _RECORD_INDEX_CACHE.get(key)
    if index is None:
        index = {}
        for record in _load_dataset_records(dataset, split):
            record_id = record.get("instance_id")
            if record_id is not None:
                index[str(record_id)] = dict(record)
        _RECORD_INDEX_CACHE[key] = index
    return index


def _load_dataset_records(dataset: str, split: str):
    try:
        from datasets import load_dataset
    except ImportError as error:
        raise ConfigError(
            "SWE-bench task context requires the optional datasets package or "
            "inline task repo/base_commit/problem_statement metadata"
        ) from error

    return load_dataset(dataset, split=split)


def _context_dataset_name(dataset: str) -> str:
    if dataset == "princeton-nlp/SWE-bench_Lite":
        return "SWE-bench/SWE-bench_Lite"
    return dataset


def _repo_url(repo: str) -> str:
    return f"https://github.com/{repo}.git"


def _git(cwd: Path, *args: str) -> None:
    result = subprocess.run(
        ("git", *args),
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise ConfigError(
            f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()}"
        )
