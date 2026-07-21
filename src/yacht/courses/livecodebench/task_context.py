"""LiveCodeBench task context loaded through the pinned runner image.

The benchmark's Hugging Face dataset uses a loading script that modern
`datasets` releases refuse to execute, so problems are loaded inside the
pinned lcb-runner container — the same environment that grades them —
and cached per process by window.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from yacht.courses.livecodebench.harness import LCB_RUNNER_IMAGE
from yacht.domain.model import ConfigError, CourseAdapter, Task


HF_CACHE_DIR = Path.home() / ".cache" / "yacht" / "lcb-hf"

_DUMP_SCRIPT = """
import json
import sys

from lcb_runner.benchmarks.code_generation import load_code_generation_dataset

problems = load_code_generation_dataset(
    sys.argv[1],
    start_date=sys.argv[2] or None,
    end_date=sys.argv[3] or None,
)
print(
    json.dumps(
        [
            {
                "question_id": problem.question_id,
                "title": problem.question_title,
                "content": problem.question_content,
                "starter_code": problem.starter_code,
                "platform": problem.platform.value,
                "contest_date": problem.contest_date.isoformat(),
            }
            for problem in problems
        ]
    )
)
"""

DumpRunner = Callable[[list[str]], str]

_WINDOW_CACHE: dict[tuple[str, str | None, str | None, str], dict[str, Any]] = {}


def task_with_livecodebench_context(
    *,
    task: Task,
    adapter: CourseAdapter,
    dump_runner: DumpRunner | None = None,
) -> Task:
    problems = load_window_problems(adapter, dump_runner=dump_runner)
    problem = problems.get(task.id)
    if problem is None:
        raise ConfigError(
            f"task {task.id} is not in the livecodebench window "
            f"{adapter.start_date}..{adapter.end_date} of {adapter.split}"
        )
    return replace(task, problem_statement=_problem_statement(problem))


def window_question_ids(
    adapter: CourseAdapter,
    *,
    dump_runner: DumpRunner | None = None,
) -> list[str]:
    return sorted(load_window_problems(adapter, dump_runner=dump_runner))


def load_window_problems(
    adapter: CourseAdapter,
    *,
    dump_runner: DumpRunner | None = None,
) -> dict[str, dict[str, Any]]:
    if adapter.start_date is None or adapter.end_date is None:
        raise ConfigError(
            "livecodebench requires start_date and end_date on the course adapter"
        )
    cache_key = (
        str(adapter.split),
        adapter.start_date,
        adapter.end_date,
        LCB_RUNNER_IMAGE,
    )
    cached = _WINDOW_CACHE.get(cache_key)
    if cached is not None:
        return cached

    runner = dump_runner if dump_runner is not None else _run_dump
    command = dump_command(adapter)
    stdout = runner(command)
    problems = _parse_problems(stdout)
    _WINDOW_CACHE[cache_key] = problems
    return problems


def dump_command(adapter: CourseAdapter) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{HF_CACHE_DIR}:{HF_CACHE_DIR}",
        "-e",
        f"HF_HOME={HF_CACHE_DIR}",
        LCB_RUNNER_IMAGE,
        "python",
        "-c",
        _DUMP_SCRIPT,
        str(adapter.split),
        str(adapter.start_date or ""),
        str(adapter.end_date or ""),
    ]


def _problem_statement(problem: dict[str, Any]) -> str:
    statement = f"{problem['title']}\n\n{problem['content']}"
    starter_code = problem.get("starter_code")
    if isinstance(starter_code, str) and starter_code.strip():
        statement += f"\n\nStarter code:\n```python\n{starter_code}\n```"
    return statement


def _parse_problems(stdout: str) -> dict[str, dict[str, Any]]:
    last_line = ""
    for line in stdout.splitlines():
        if line.strip().startswith("["):
            last_line = line
    if not last_line:
        raise ConfigError("livecodebench problem dump produced no JSON problem list")
    try:
        payload = json.loads(last_line)
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"livecodebench problem dump is not valid JSON: {error}"
        ) from error
    if not isinstance(payload, list) or not payload:
        raise ConfigError("livecodebench problem dump must be a non-empty JSON array")
    problems: dict[str, dict[str, Any]] = {}
    for entry in payload:
        if not isinstance(entry, dict) or not isinstance(entry.get("question_id"), str):
            raise ConfigError(
                "livecodebench problem dump entries must be objects with question_id"
            )
        problems[str(entry["question_id"])] = entry
    return problems


def _run_dump(command: list[str]) -> str:
    HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-2000:]
        raise ConfigError(
            "livecodebench problem dump failed with exit code "
            f"{completed.returncode}: {detail}"
        )
    return completed.stdout
