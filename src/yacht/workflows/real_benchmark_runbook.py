from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from yacht.workflows.benchmark_execution_plan import BENCHMARK_EXECUTION_PLAN_PATH
from yacht.workflows.benchmark_grading_collection import BENCHMARK_GRADING_COLLECTION_PATH
from yacht.workflows.benchmark_launch import BENCHMARK_LAUNCH_RESULT_PATH
from yacht.workflows.benchmark_launcher_handoff import (
    BENCHMARK_LAUNCHER_HANDOFF_PATH,
    DEFAULT_SWEBENCH_PYTHON_EXECUTABLE,
)
from yacht.reports.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.courses.handoff import COURSE_HANDOFF_PATH
from yacht.reports.preflight_evidence import PREFLIGHT_EVIDENCE_REPORT_PATH
from yacht.workflows.real_benchmark_eval import REAL_BENCHMARK_EVAL_PATH
from yacht.domain.model import (
    Comparison,
    ConfigError,
    Regatta,
    SecretReference,
    Vessel,
    load_regatta,
)
from yacht.runtimes.instances import RUNTIME_INSTANCES_PLAN_PATH
from yacht.runtimes.capabilities import rigging_capabilities_to_json
from yacht.schemas import (
    REAL_BENCHMARK_RUNBOOK_SCHEMA,
    validate_real_benchmark_runbook_document,
)
from yacht.surface_metadata import regatta_surfaces_to_json
from yacht.courses.swe_bench.artifacts import candidate_patches_path
from yacht.reports.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH


REAL_BENCHMARK_RUNBOOK_PATH = Path("real-benchmark-runbook.json")
BENCHMARK_REPORT_PATH = Path("benchmark-report.md")


def write_real_benchmark_runbook(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    max_workers: int = 1,
    python_executable: str = DEFAULT_SWEBENCH_PYTHON_EXECUTABLE,
) -> dict[str, Any]:
    runbook = build_real_benchmark_runbook(
        config_path=config_path,
        logbook_dir=logbook_dir,
        workspace_path=workspace_path,
        max_workers=max_workers,
        python_executable=python_executable,
    )
    _write_json(logbook_dir / REAL_BENCHMARK_RUNBOOK_PATH, runbook)
    return runbook


def render_real_benchmark_runbook(runbook: dict[str, Any]) -> str:
    lines = [
        "## Real Benchmark Runbook",
        "",
        f"- Regatta: `{runbook['regatta']}`",
        f"- Course: `{runbook['course']}`",
        f"- Agent: `{runbook['agent']}`",
        f"- Tools: `{_surface_tools(runbook)}`",
        "",
        "### Runtime Capabilities",
        "",
        *_runtime_capability_lines(runbook),
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
            f"- Course handoff: `{artifacts['course_handoff']}`",
            "- Preflight:",
            *[f"  - `{path}`" for path in artifacts["preflight"]],
            f"- Preflight evidence report: `{artifacts['preflight_evidence_report']}`",
            "- Task attempts:",
            *[f"  - `{path}`" for path in artifacts["task_attempts"]],
            f"- Task attempt scorecard: `{artifacts['task_attempt_scorecard']}`",
            "- Candidate patches:",
            *[f"  - `{path}`" for path in artifacts["candidate_patches"]],
            f"- Runtime instances: `{artifacts['runtime_instances']}`",
            f"- Benchmark execution plan: `{artifacts['benchmark_execution_plan']}`",
            f"- Benchmark launcher handoff: `{artifacts['benchmark_launcher_handoff']}`",
            f"- Benchmark launch result: `{artifacts['benchmark_launch_result']}`",
            f"- Benchmark grading collection: `{artifacts['benchmark_grading_collection']}`",
            f"- Benchmark scorecard: `{artifacts['benchmark_scorecard']}`",
            f"- Benchmark report: `{artifacts['benchmark_report']}`",
            f"- Real benchmark eval: `{artifacts['real_benchmark_eval']}`",
            f"- Real benchmark runbook: `{artifacts['real_benchmark_runbook']}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_real_benchmark_runbook(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    max_workers: int,
    python_executable: str,
) -> dict[str, Any]:
    if max_workers < 1:
        raise ConfigError("max_workers must be an integer >= 1")
    regatta = load_regatta(config_path)
    artifacts = _artifacts(regatta, logbook_dir)
    inspection_target = _inspection_target(regatta)
    secret_placeholders = _secret_placeholders(regatta)
    surfaces = regatta_surfaces_to_json(regatta)
    runbook = {
        "schema": REAL_BENCHMARK_RUNBOOK_SCHEMA,
        "regatta": regatta.name,
        "course": regatta.course.name,
        "agent": _primary_agent(surfaces),
        "surfaces": surfaces,
        "rigging_capabilities": _rigging_capabilities(regatta),
        "secret_placeholders": secret_placeholders,
        "steps": _steps(
            config_path=config_path,
            logbook_dir=logbook_dir,
            workspace_path=workspace_path,
            max_workers=max_workers,
            python_executable=python_executable,
            secret_placeholders=secret_placeholders,
            artifacts=artifacts,
            inspection_target=inspection_target,
        ),
        "artifacts": artifacts,
    }
    validate_real_benchmark_runbook_document(runbook)
    return runbook


def _primary_agent(surfaces: dict[str, Any]) -> str:
    agents = surfaces.get("agent_harnesses", [])
    if isinstance(agents, list) and agents and isinstance(agents[0], str):
        return agents[0]
    return "unknown"


def _surface_tools(runbook: dict[str, Any]) -> str:
    surfaces = runbook.get("surfaces", {})
    if not isinstance(surfaces, dict):
        return "none"
    tools = surfaces.get("tools", [])
    if not isinstance(tools, list) or not tools:
        return "none"
    return ", ".join(str(tool) for tool in tools)


def _runtime_capability_lines(runbook: dict[str, Any]) -> list[str]:
    capabilities = runbook.get("rigging_capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        return ["- None"]
    return [
        "- "
        f"`{capability['vessel']}`: `{capability['status']}` "
        f"({capability['runtime_backend']}; "
        f"methods={', '.join(capability['supported_install_methods']) or 'none'})"
        for capability in capabilities
        if isinstance(capability, dict)
    ]


def _rigging_capabilities(regatta: Regatta) -> list[dict[str, Any]]:
    capabilities = []
    for vessel in regatta.vessels:
        if vessel.runtime is None:
            continue
        runtime = regatta.runtime_recipes[vessel.runtime]
        riggings = tuple(regatta.rigging_recipes[name] for name in vessel.rigging)
        payload = rigging_capabilities_to_json(runtime, riggings)
        payload["vessel"] = vessel.name
        payload["runtime"] = runtime.name
        capabilities.append(payload)
    return capabilities


def _steps(
    *,
    config_path: Path,
    logbook_dir: Path,
    workspace_path: Path,
    max_workers: int,
    python_executable: str,
    secret_placeholders: list[dict[str, str]],
    artifacts: dict[str, Any],
    inspection_target: dict[str, str],
) -> list[dict[str, Any]]:
    secrets = " ".join(placeholder["argument"] for placeholder in secret_placeholders)
    secret_suffix = f" {secrets}" if secrets else ""
    python_suffix = ""
    if python_executable != DEFAULT_SWEBENCH_PYTHON_EXECUTABLE:
        python_suffix = f" --python-executable {_quote_text(python_executable)}"
    benchmark_eval_command = (
        "uv run yacht real-benchmark-eval "
        f"{_quote(config_path)} --logbook {_quote(logbook_dir)} "
        f"--workspace {_quote(workspace_path)}{secret_suffix} "
        f"--max-workers {max_workers}"
        f"{python_suffix}"
    )
    return [
        {
            "name": "real-benchmark-eval",
            "command": benchmark_eval_command,
            "artifacts": [
                artifacts["real_benchmark_eval"],
                artifacts["course_handoff"],
                *artifacts["preflight"],
                artifacts["preflight_evidence_report"],
                *artifacts["task_attempts"],
                artifacts["task_attempt_scorecard"],
                *artifacts["candidate_patches"],
                artifacts["runtime_instances"],
                artifacts["benchmark_execution_plan"],
                artifacts["benchmark_launcher_handoff"],
                artifacts["benchmark_launch_result"],
                artifacts["benchmark_grading_collection"],
                artifacts["benchmark_scorecard"],
            ],
        },
        {
            "name": "benchmark-status",
            "command": f"uv run yacht benchmark-status --logbook {_quote(logbook_dir)}",
            "artifacts": [
                artifacts["real_benchmark_eval"],
                artifacts["benchmark_scorecard"],
            ],
        },
        {
            "name": "benchmark-report",
            "command": f"uv run yacht benchmark-report --logbook {_quote(logbook_dir)}",
            "artifacts": [artifacts["benchmark_scorecard"]],
        },
        {
            "name": "benchmark-report-filtered",
            "command": _filtered_report_command(
                logbook_dir=logbook_dir,
                target=inspection_target,
            ),
            "artifacts": [artifacts["benchmark_scorecard"]],
        },
        {
            "name": "benchmark-report-markdown",
            "command": (
                f"uv run yacht benchmark-report --logbook {_quote(logbook_dir)} "
                f"--format markdown --output {_quote(logbook_dir / BENCHMARK_REPORT_PATH)}"
            ),
            "artifacts": [artifacts["benchmark_report"]],
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
        argument = f"--secret {name}=@env:{secret.name}"
    else:
        argument = f'--secret {name}="{{secret:{name}}}"'
    return {
        "name": name,
        "source": secret.source,
        "ref": ref,
        "argument": argument,
    }


def _artifacts(regatta: Regatta, logbook_dir: Path) -> dict[str, Any]:
    handoff = {
        "adapter": {
            "kind": regatta.course.adapter.kind,
        },
    }
    return {
        "course_handoff": str(logbook_dir / COURSE_HANDOFF_PATH),
        "preflight": [
            str(logbook_dir / "preflight" / comparison.name / f"{vessel_name}.json")
            for comparison in regatta.comparisons
            for vessel_name in comparison.vessels
        ],
        "preflight_evidence_report": str(logbook_dir / PREFLIGHT_EVIDENCE_REPORT_PATH),
        "task_attempts": [
            str(_task_attempt_path(logbook_dir, comparison, vessel, task_id))
            for comparison in regatta.comparisons
            for vessel in _comparison_vessels(regatta, comparison)
            for task_id in (task.id for task in regatta.course.tasks)
        ],
        "task_attempt_scorecard": str(logbook_dir / TASK_ATTEMPT_SCORECARD_PATH),
        "candidate_patches": [
            str(
                candidate_patches_path(
                    logbook_dir=logbook_dir,
                    handoff=handoff,
                    vessel_name=vessel_name,
                )
            )
            for comparison in regatta.comparisons
            for vessel_name in comparison.vessels
        ],
        "runtime_instances": str(logbook_dir / RUNTIME_INSTANCES_PLAN_PATH),
        "benchmark_execution_plan": str(logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH),
        "benchmark_launcher_handoff": str(logbook_dir / BENCHMARK_LAUNCHER_HANDOFF_PATH),
        "benchmark_launch_result": str(logbook_dir / BENCHMARK_LAUNCH_RESULT_PATH),
        "benchmark_grading_collection": str(
            logbook_dir / BENCHMARK_GRADING_COLLECTION_PATH
        ),
        "benchmark_scorecard": str(logbook_dir / BENCHMARK_SCORECARD_PATH),
        "benchmark_report": str(logbook_dir / BENCHMARK_REPORT_PATH),
        "real_benchmark_eval": str(logbook_dir / REAL_BENCHMARK_EVAL_PATH),
        "real_benchmark_runbook": str(logbook_dir / REAL_BENCHMARK_RUNBOOK_PATH),
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


def _inspection_target(regatta: Regatta) -> dict[str, str]:
    comparison = regatta.comparisons[0]
    vessel_name = comparison.vessels[-1]
    task_id = regatta.course.tasks[0].id
    return {
        "vessel": vessel_name,
        "task": task_id,
    }


def _filtered_report_command(
    *,
    logbook_dir: Path,
    target: dict[str, str],
) -> str:
    return (
        f"uv run yacht benchmark-report --logbook {_quote(logbook_dir)} "
        f"--vessel {_quote_text(target['vessel'])} "
        f"--task {_quote_text(target['task'])}"
    )


def _quote(value: Path) -> str:
    return shlex.quote(str(value))


def _quote_text(value: str) -> str:
    return shlex.quote(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
