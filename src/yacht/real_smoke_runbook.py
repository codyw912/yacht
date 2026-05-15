from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from yacht.regatta import (
    Comparison,
    ConfigError,
    Regatta,
    SecretReference,
    Vessel,
    load_regatta,
)
from yacht.schemas import (
    REAL_SMOKE_RUNBOOK_SCHEMA,
    validate_real_smoke_runbook_document,
)
from yacht.smoke_report import SMOKE_REPORT_PATH


REAL_SMOKE_RUNBOOK_PATH = Path("real-smoke-runbook.json")


def write_real_smoke_runbook(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    runbook = build_real_smoke_runbook(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
    )
    _write_json(logbook_dir / REAL_SMOKE_RUNBOOK_PATH, runbook)
    return runbook


def render_real_smoke_runbook(runbook: dict[str, Any]) -> str:
    lines = [
        "## Real Smoke Runbook",
        "",
        f"- Regatta: `{runbook['regatta']}`",
        f"- Course: `{runbook['course']}`",
        f"- Agent: `{runbook['agent']}`",
        "",
        "### Secrets",
        "",
    ]
    if runbook["secret_placeholders"]:
        lines.extend(
            f"- `{placeholder['name']}` from `{placeholder['ref']}`: "
            f"`{placeholder['argument']}`"
            for placeholder in runbook["secret_placeholders"]
        )
    else:
        lines.append("- None")
    lines.extend(["", "### Commands", ""])
    for step in runbook["steps"]:
        lines.extend(
            [
                f"#### {step['name']}",
                "",
                "```sh",
                step["command"],
                "```",
                "",
            ]
        )
    lines.extend(["### Expected Artifacts", ""])
    artifacts = runbook["artifacts"]
    lines.extend(
        [
            "- Preflight:",
            *[f"  - `{path}`" for path in artifacts["preflight"]],
            "- Task attempts:",
            *[f"  - `{path}`" for path in artifacts["task_attempts"]],
            f"- Task attempt scorecard: `{artifacts['task_attempt_scorecard']}`",
            f"- Smoke readiness report: `{artifacts['smoke_readiness_report']}`",
            f"- Smoke report: `{artifacts['smoke_report']}`",
            f"- Real smoke runbook: `{artifacts['real_smoke_runbook']}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_real_smoke_runbook(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    regatta = load_regatta(config_path)
    artifacts = _artifacts(regatta, logbook_dir)
    secret_placeholders = _secret_placeholders(regatta)
    steps = _steps(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
        secret_placeholders=secret_placeholders,
        artifacts=artifacts,
    )
    runbook = {
        "schema": REAL_SMOKE_RUNBOOK_SCHEMA,
        "regatta": regatta.name,
        "course": regatta.course.name,
        "agent": "pi",
        "secret_placeholders": secret_placeholders,
        "steps": steps,
        "artifacts": artifacts,
    }
    validate_real_smoke_runbook_document(runbook)
    return runbook


def _steps(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    secret_placeholders: list[dict[str, str]],
    artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    secrets = " ".join(placeholder["argument"] for placeholder in secret_placeholders)
    secret_suffix = f" {secrets}" if secrets else ""
    return [
        {
            "name": "real-smoke-eval",
            "command": (
                "uv run yacht real-smoke-eval "
                f"{_quote(config_path)} --logbook {_quote(logbook_dir)} "
                f"--workspace {_quote(workspace_path)}{secret_suffix}"
            ),
            "artifacts": [
                *artifacts["preflight"],
                *artifacts["task_attempts"],
                artifacts["task_attempt_scorecard"],
                artifacts["smoke_readiness_report"],
                artifacts["smoke_report"],
            ],
        },
        {
            "name": "preflight",
            "command": (
                "uv run yacht preflight "
                f"{_quote(config_path)} --agent-preflight pi "
                f"--logbook {_quote(logbook_dir)} "
                f"--workspace {_quote(workspace_path)}{secret_suffix}"
            ),
            "artifacts": artifacts["preflight"],
        },
        {
            "name": "task-attempts",
            "command": (
                "uv run yacht task-attempts "
                f"{_quote(config_path)} --agent pi --logbook {_quote(logbook_dir)} "
                f"--workspace {_quote(workspace_path)}{secret_suffix}"
            ),
            "artifacts": artifacts["task_attempts"],
        },
        {
            "name": "pi-smoke-eval",
            "command": (
                "uv run yacht pi-smoke-eval "
                f"{_quote(config_path)} --logbook {_quote(logbook_dir)} "
                f"--workspace {_quote(workspace_path)}{secret_suffix}"
            ),
            "artifacts": [
                *artifacts["task_attempts"],
                artifacts["task_attempt_scorecard"],
            ],
        },
        {
            "name": "smoke-readiness-report",
            "command": (
                f"uv run yacht smoke-readiness-report --logbook {_quote(logbook_dir)}"
            ),
            "artifacts": [artifacts["smoke_readiness_report"]],
        },
        {
            "name": "smoke-report",
            "command": f"uv run yacht smoke-report --logbook {_quote(logbook_dir)}",
            "artifacts": [artifacts["smoke_report"]],
        },
    ]


def _secret_placeholders(regatta: Regatta) -> list[dict[str, str]]:
    return [
        _secret_placeholder(name, secret)
        for name, secret in sorted(regatta.secrets.items())
    ]


def _secret_placeholder(name: str, secret: SecretReference) -> dict[str, str]:
    ref = secret.name or secret.path or f"secret:{name}"
    if secret.source == "env" and secret.name:
        argument = f'--secret {name}="${secret.name}"'
    else:
        argument = f'--secret {name}="{{secret:{name}}}"'
    return {
        "name": name,
        "source": secret.source,
        "ref": ref,
        "argument": argument,
    }


def _artifacts(regatta: Regatta, logbook_dir: Path) -> dict[str, Any]:
    return {
        "preflight": [
            str(logbook_dir / "preflight" / comparison.name / f"{vessel_name}.json")
            for comparison in regatta.comparisons
            for vessel_name in comparison.vessels
        ],
        "task_attempts": [
            str(_task_attempt_path(logbook_dir, comparison, vessel, task_id))
            for comparison in regatta.comparisons
            for vessel in _comparison_vessels(regatta, comparison)
            for task_id in (task.id for task in regatta.course.tasks)
        ],
        "task_attempt_scorecard": str(logbook_dir / "task-attempt-scorecard.json"),
        "smoke_readiness_report": str(logbook_dir / "smoke-readiness-report.json"),
        "smoke_report": str(logbook_dir / SMOKE_REPORT_PATH),
        "real_smoke_runbook": str(logbook_dir / REAL_SMOKE_RUNBOOK_PATH),
    }


def _comparison_vessels(regatta: Regatta, comparison: Comparison) -> list[Vessel]:
    return [_vessel_by_name(regatta, vessel_name) for vessel_name in comparison.vessels]


def _vessel_by_name(regatta: Regatta, name: str) -> Vessel:
    for vessel in regatta.vessels:
        if vessel.name == name:
            return vessel
    raise ConfigError(f"comparison references undefined vessel {name}")


def _task_attempt_path(
    logbook_dir: Path,
    comparison: Comparison,
    vessel: Vessel,
    task_id: str,
) -> Path:
    return (
        logbook_dir
        / "task-attempts"
        / comparison.name
        / vessel.name
        / f"{task_id}.json"
    )


def _quote(value: Path) -> str:
    return shlex.quote(str(value))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
