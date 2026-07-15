from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

from yacht.config.loader import load_regatta
from yacht.domain.model import ConfigError
from yacht.preflight.execution import CommandResult
from yacht.workflows.benchmark_launcher_handoff import (
    DEFAULT_SWEBENCH_PYTHON_EXECUTABLE,
)

CommandRunner = Callable[[tuple[str, ...]], CommandResult]
WhichResolver = Callable[[str], str | None]


def run_doctor(
    *,
    config_path: Path | None,
    logbook_dir: Path,
    check_swebench: bool = True,
    which: WhichResolver = shutil.which,
    command_runner: CommandRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    runner = command_runner or _run_host_command
    host_env = os.environ if env is None else env
    checks = [
        _python_check(),
        _binary_check("uv", which, hint="install uv from https://docs.astral.sh/uv/"),
        _binary_check("git", which, hint="install git and ensure it is on PATH"),
    ]
    docker_check = _binary_check(
        "docker",
        which,
        hint="install Docker and ensure the docker CLI is on PATH",
    )
    checks.append(docker_check)
    checks.append(_docker_daemon_check(runner, docker_check["status"] == "passed"))
    checks.append(_logbook_writable_check(logbook_dir))
    if check_swebench:
        checks.append(_swebench_check(runner))
    if config_path is not None:
        checks.extend(_config_checks(config_path, runner, host_env))

    failed = [check["name"] for check in checks if check["status"] == "failed"]
    warnings = [check["name"] for check in checks if check["status"] == "warning"]
    return {
        "status": "failed" if failed else "passed",
        "failed": failed,
        "warnings": warnings,
        "checks": checks,
    }


def render_doctor_report(report: dict[str, Any], output_format: str = "text") -> str:
    if output_format == "json":
        return json.dumps(report, indent=2) + "\n"
    lines = [f"YACHT doctor: {report['status']}"]
    for check in report["checks"]:
        marker = {
            "passed": "pass",
            "failed": "FAIL",
            "warning": "warn",
            "skipped": "skip",
        }[check["status"]]
        lines.append(f"[{marker}] {check['name']}: {check['detail']}")
        if check.get("hint"):
            lines.append(f"       hint: {check['hint']}")
    return "\n".join(lines) + "\n"


def _python_check() -> dict[str, Any]:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info < (3, 12):
        return _check(
            "python",
            "failed",
            f"running Python {version}",
            hint="YACHT requires Python 3.12 or newer",
        )
    return _check("python", "passed", f"running Python {version}")


def _binary_check(name: str, which: WhichResolver, *, hint: str) -> dict[str, Any]:
    path = which(name)
    if path is None:
        return _check(name, "failed", f"{name} not found on PATH", hint=hint)
    return _check(name, "passed", path)


def _docker_daemon_check(runner: CommandRunner, cli_present: bool) -> dict[str, Any]:
    if not cli_present:
        return _check(
            "docker-daemon",
            "skipped",
            "skipped because the docker CLI is missing",
        )
    result = runner(("docker", "info", "--format", "{{.ServerVersion}}"))
    if result.exit_code != 0:
        return _check(
            "docker-daemon",
            "failed",
            f"docker info failed: {result.stderr.strip() or result.stdout.strip()}",
            hint="start Docker and re-run yacht doctor",
        )
    return _check("docker-daemon", "passed", f"server {result.stdout.strip()}")


def _logbook_writable_check(logbook_dir: Path) -> dict[str, Any]:
    probe = logbook_dir.resolve()
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            break
        probe = parent
    if probe.is_dir() and os.access(probe, os.W_OK):
        return _check("logbook-path", "passed", f"{logbook_dir} is writable")
    return _check(
        "logbook-path",
        "failed",
        f"cannot write to {logbook_dir} (nearest existing path: {probe})",
        hint="pass --logbook with a writable directory",
    )


def _swebench_check(runner: CommandRunner) -> dict[str, Any]:
    argv = (
        *shlex.split(DEFAULT_SWEBENCH_PYTHON_EXECUTABLE),
        "-c",
        "import swebench",
    )
    result = runner(argv)
    if result.exit_code != 0:
        return _check(
            "swebench-harness",
            "failed",
            f"uv could not resolve swebench ({DEFAULT_SWEBENCH_PYTHON_EXECUTABLE})",
            hint=(
                "no manual install is needed: uv fetches swebench on demand, "
                "but the first resolution requires network access; re-run "
                "with network or use --skip-swebench"
            ),
        )
    return _check(
        "swebench-harness",
        "passed",
        "swebench resolves on demand via uv (cached after first run)",
    )


def _config_checks(
    config_path: Path,
    runner: CommandRunner,
    env: Mapping[str, str],
) -> list[dict[str, Any]]:
    try:
        regatta = load_regatta(config_path)
    except ConfigError as error:
        return [
            _check(
                "config",
                "failed",
                f"{config_path} is invalid: {error}",
                hint="fix the config or run yacht validate for details",
            )
        ]
    checks = [_check("config", "passed", f"{config_path} is a valid regatta config")]
    for name, runtime in sorted(regatta.runtime_recipes.items()):
        if runtime.backend != "container" or runtime.image is None:
            continue
        result = runner(("docker", "image", "inspect", runtime.image))
        if result.exit_code != 0:
            checks.append(
                _check(
                    f"runtime-image:{name}",
                    "failed",
                    f"image {runtime.image} is not available locally",
                    hint=(
                        f"build it, for example: docker build -t {runtime.image} "
                        "containers/pi-agent-runtime"
                    ),
                )
            )
        else:
            checks.append(_check(f"runtime-image:{name}", "passed", runtime.image))
    for name, secret in sorted(regatta.secrets.items()):
        if secret.source != "env" or secret.name is None:
            continue
        if secret.name in env:
            checks.append(_check(f"secret:{name}", "passed", f"${secret.name} is set"))
        else:
            checks.append(
                _check(
                    f"secret:{name}",
                    "warning",
                    f"${secret.name} is not set",
                    hint=(
                        f"export {secret.name} or pass "
                        f"--secret {name}=... when running the eval"
                    ),
                )
            )
    return checks


def _check(
    name: str,
    status: str,
    detail: str,
    *,
    hint: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": name, "status": status, "detail": detail}
    if hint is not None:
        payload["hint"] = hint
    return payload


def _run_host_command(argv: tuple[str, ...]) -> CommandResult:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        return CommandResult(exit_code=127, stdout="", stderr=str(error))
    return CommandResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
