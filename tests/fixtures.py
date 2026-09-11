import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


def create_fixture_repo(path: Path) -> Path:
    path.mkdir()
    git_output(path, "init")
    git_output(path, "config", "user.email", "test@example.com")
    git_output(path, "config", "user.name", "Test User")
    git_output(path, "config", "commit.gpgsign", "false")
    (path / "example.txt").write_text("base\n", encoding="utf-8")
    git_output(path, "add", "example.txt")
    git_output(path, "commit", "-m", "base")
    (path / "example.txt").write_text("later\n", encoding="utf-8")
    git_output(path, "commit", "-am", "later")
    return path


def fixture_repo_base_commit(path: Path) -> str:
    return git_output(path, "rev-list", "--max-parents=0", "HEAD")


_DATASET_TASK_LINE = (
    '{ id = "django__django-11099", title = "Fix a regression", difficulty = 3 }'
)


def hermetic_swe_bench_config(config: str, repo: Path) -> str:
    inline_task_line = (
        '{ id = "django__django-11099", title = "Fix a regression", '
        'difficulty = 3, repo = "django/django", '
        f'repo_url = "{repo}", base_commit = "{fixture_repo_base_commit(repo)}", '
        'problem_statement = "Fix the regression." }'
    )
    if _DATASET_TASK_LINE not in config:
        raise AssertionError(
            "fixture config no longer contains the expected task line; "
            "update hermetic_swe_bench_config so these tests stay offline"
        )
    return config.replace(_DATASET_TASK_LINE, inline_task_line)


def git_output(path: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=path,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


@contextmanager
def docker_endpoint_selection(
    *,
    host: str | None = None,
    context: str | None = None,
):
    saved_host = os.environ.get("DOCKER_HOST")
    saved_context = os.environ.get("DOCKER_CONTEXT")
    try:
        if host is None:
            os.environ.pop("DOCKER_HOST", None)
        else:
            os.environ["DOCKER_HOST"] = host
        if context is None:
            os.environ.pop("DOCKER_CONTEXT", None)
        else:
            os.environ["DOCKER_CONTEXT"] = context
        yield
    finally:
        if saved_host is None:
            os.environ.pop("DOCKER_HOST", None)
        else:
            os.environ["DOCKER_HOST"] = saved_host
        if saved_context is None:
            os.environ.pop("DOCKER_CONTEXT", None)
        else:
            os.environ["DOCKER_CONTEXT"] = saved_context


@contextmanager
def mock_docker_context_host(host: str):
    def fake_run(argv, *args, **kwargs):
        command = [str(part) for part in argv]
        if (
            len(command) >= 3
            and command[0] == "docker"
            and "context" in command
            and "inspect" in command
        ):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=host + "\n",
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    with patch("subprocess.run", side_effect=fake_run):
        yield


@contextmanager
def offline_docker_socket():
    with (
        docker_endpoint_selection(host=None, context=None),
        mock_docker_context_host("unix:///var/run/docker.sock"),
    ):
        yield


REGATTA_CONFIG = """
[regatta]
name = "memory-smoke-test"

[course]
name = "tiny-course"
tasks = [
  { id = "task-1", title = "Fix a failing test", difficulty = 1 },
  { id = "task-2", title = "Add a CLI flag", difficulty = 2 },
]

[[vessels]]
name = "baseline"
model = "mock-fast"

[[vessels]]
name = "memory-rig"
model = "mock-fast"
rigging = ["memory"]
"""


INVALID_REGATTA_CONFIG = """
[regatta]
name = "broken-regatta"

[course]
name = "tiny-course"
tasks = []

[[vessels]]
name = "baseline"
model = "mock-fast"
"""
