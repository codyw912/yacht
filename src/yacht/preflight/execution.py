from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from yacht.domain.model import (
    Comparison,
    ConfigError,
    PreflightCheck,
    Regatta,
    RiggingRecipe,
    RuntimeInstance,
    RuntimeRecipe,
    SecretReference,
    Vessel,
)
from yacht.logbook.io import write_json
from yacht.runtimes.process import subprocess_env
from yacht.contracts.schemas import PREFLIGHT_SCHEMA, validate_preflight_document


MACHINE_CHECK_KINDS = {
    "command",
    "env",
    "install-only",
    "path-isolation",
    "runtime-capability",
}
AGENT_CHECK_KINDS = {"agent-prompt"}


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class AgentPromptResult:
    exit_code: int
    response: str
    tool_calls: tuple[str, ...]
    transcript_path: Path | None = None


@dataclass(frozen=True)
class EffectiveCheck:
    check: PreflightCheck
    required: bool
    origin: str
    origin_name: str


CommandRunner = Callable[[tuple[str, ...], dict[str, str], Path], CommandResult]
AgentPromptRunner = Callable[[str, dict[str, str], Path], AgentPromptResult]


def execute_machine_preflight(
    *,
    regatta: Regatta,
    vessel: Vessel,
    instance: RuntimeInstance,
    artifact_path: Path,
    comparison: Comparison | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    return _execute_preflight(
        regatta=regatta,
        vessel=vessel,
        instance=instance,
        artifact_path=artifact_path,
        comparison=comparison,
        command_runner=command_runner,
        agent_prompt_runner=None,
        include_agent_checks=False,
    )


def execute_preflight(
    *,
    regatta: Regatta,
    vessel: Vessel,
    instance: RuntimeInstance,
    artifact_path: Path,
    comparison: Comparison | None = None,
    command_runner: CommandRunner | None = None,
    agent_prompt_runner: AgentPromptRunner | None = None,
) -> dict[str, object]:
    return _execute_preflight(
        regatta=regatta,
        vessel=vessel,
        instance=instance,
        artifact_path=artifact_path,
        comparison=comparison,
        command_runner=command_runner,
        agent_prompt_runner=agent_prompt_runner,
        include_agent_checks=True,
    )


def _execute_preflight(
    *,
    regatta: Regatta,
    vessel: Vessel,
    instance: RuntimeInstance,
    artifact_path: Path,
    comparison: Comparison | None,
    command_runner: CommandRunner | None,
    agent_prompt_runner: AgentPromptRunner | None,
    include_agent_checks: bool,
) -> dict[str, object]:
    runner = command_runner or _run_command
    runtime = instance.runtime
    riggings = tuple(regatta.rigging_recipes[name] for name in vessel.rigging)
    checks = _preflight_checks(runtime, riggings, include_agent_checks)
    if not checks:
        raise ConfigError(
            f"vessel {vessel.name} has no preflight checks: add checks to "
            f"runtime {runtime.name} or its riggings under "
            "[runtimes.<name>.preflight] before running an eval"
        )
    check_results = [
        _execute_check(
            check,
            instance,
            runner,
            agent_prompt_runner,
            regatta=regatta,
            vessel=vessel,
        )
        for check in checks
    ]
    artifact = {
        "schema": PREFLIGHT_SCHEMA,
        "regatta": regatta.name,
        "vessel": vessel.name,
        "runtime": runtime.name,
        "workspace_path": str(instance.workspace_path),
        "temp_home": str(instance.temp_home),
        "command_prefix": list(instance.command_prefix),
        "cleanup_paths": [str(path) for path in instance.cleanup_paths],
        "runtime_setup": [
            {
                "origin": result.origin,
                "origin_name": result.origin_name,
                "action": result.action,
                "target": result.target,
                "argv": list(result.argv),
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            for result in instance.setup_results
        ],
        "status": _artifact_status(check_results),
        "failure_policy": regatta.preflight.failure_policy,
        "secret_refs": [
            _secret_ref_to_json(name, regatta.secrets[name])
            for name in _required_secret_names(runtime, riggings)
        ],
        "checks": check_results,
    }
    if comparison is not None:
        artifact["comparison"] = comparison.name

    validate_preflight_document(artifact)
    write_json(artifact_path, artifact)
    return artifact


def _run_command(
    argv: tuple[str, ...],
    env: dict[str, str],
    cwd: Path,
) -> CommandResult:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=subprocess_env(argv, env),
        capture_output=True,
        check=False,
        text=True,
    )
    return CommandResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _preflight_checks(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
    include_agent_checks: bool,
) -> list[EffectiveCheck]:
    kinds = set(MACHINE_CHECK_KINDS)
    if include_agent_checks:
        kinds.update(AGENT_CHECK_KINDS)
    checks = [
        EffectiveCheck(
            check=check,
            required=runtime.preflight.required and check.required,
            origin="runtime",
            origin_name=runtime.name,
        )
        for check in runtime.preflight.checks
        if check.kind in kinds
    ]
    for rigging in riggings:
        checks.extend(
            EffectiveCheck(
                check=check,
                required=rigging.preflight.required and check.required,
                origin="rigging",
                origin_name=rigging.name,
            )
            for check in rigging.preflight.checks
            if check.kind in kinds
        )
    return checks


def _execute_check(
    effective_check: EffectiveCheck,
    instance: RuntimeInstance,
    command_runner: CommandRunner,
    agent_prompt_runner: AgentPromptRunner | None,
    *,
    regatta: Regatta,
    vessel: Vessel,
) -> dict[str, object]:
    check = effective_check.check
    if check.kind == "command":
        return _execute_command_check(effective_check, instance, command_runner)
    if check.kind == "env":
        return _execute_env_check(effective_check, instance)
    if check.kind == "path-isolation":
        return _execute_path_isolation_check(effective_check, instance)
    if check.kind == "runtime-capability":
        return _execute_runtime_capability_check(effective_check)
    if check.kind == "install-only":
        return _execute_install_only_check(
            effective_check,
            instance,
            command_runner,
            regatta=regatta,
            vessel=vessel,
        )
    if check.kind == "agent-prompt":
        return _execute_agent_prompt_check(
            effective_check, instance, agent_prompt_runner
        )
    raise ValueError(f"unsupported preflight check kind {check.kind}")


def _execute_command_check(
    effective_check: EffectiveCheck,
    instance: RuntimeInstance,
    command_runner: CommandRunner,
) -> dict[str, object]:
    check = effective_check.check
    argv = instance.command_prefix + check.command
    result = command_runner(argv, instance.env, instance.workspace_path)
    return {
        **_check_result_base(effective_check),
        "status": "passed" if result.exit_code == 0 else "failed",
        "evidence": {
            "argv": list(argv),
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    }


def _execute_env_check(
    effective_check: EffectiveCheck,
    instance: RuntimeInstance,
) -> dict[str, object]:
    check = effective_check.check
    missing = [name for name in check.env if name not in instance.env]
    present = {name: instance.env[name] for name in check.env if name in instance.env}
    evidence: dict[str, object] = {"present_env": present}
    if missing:
        evidence["missing_env"] = missing
    return {
        **_check_result_base(effective_check),
        "status": "failed" if missing else "passed",
        "evidence": evidence,
    }


def _execute_path_isolation_check(
    effective_check: EffectiveCheck,
    instance: RuntimeInstance,
) -> dict[str, object]:
    check = effective_check.check
    missing = [name for name in check.env if name not in instance.env]
    resolved_paths = {
        name: instance.env[name] for name in check.env if name in instance.env
    }
    isolation_root = _isolation_root(instance)
    outside_trial_home = {
        name: value
        for name, value in resolved_paths.items()
        if not _is_under(isolation_root, Path(value))
    }
    evidence: dict[str, object] = {"paths": resolved_paths}
    if missing:
        evidence["missing_env"] = missing
    if outside_trial_home:
        evidence["outside_trial_home"] = outside_trial_home
    status = "failed" if missing or outside_trial_home else "passed"
    return {
        **_check_result_base(effective_check),
        "status": status,
        "evidence": evidence,
    }


def _execute_install_only_check(
    effective_check: EffectiveCheck,
    instance: RuntimeInstance,
    command_runner: CommandRunner,
    *,
    regatta: Regatta,
    vessel: Vessel,
) -> dict[str, object]:
    if instance.runtime.backend != "harbor":
        return {
            **_check_result_base(effective_check),
            "status": "failed",
            "evidence": {
                "error": (
                    "install-only checks require the harbor runtime backend, "
                    f"got {instance.runtime.backend}"
                ),
            },
        }

    from yacht.courses.terminal_bench.install_only import (
        run_terminal_bench_install_only,
    )

    def runner(argv: tuple[str, ...], cwd: Path) -> CommandResult:
        return command_runner(argv, instance.env, cwd)

    try:
        result = run_terminal_bench_install_only(
            regatta=regatta,
            vessel_name=vessel.name,
            work_dir=instance.temp_home / "install-only",
            command_runner=runner,
        )
    except ConfigError as error:
        return {
            **_check_result_base(effective_check),
            "status": "failed",
            "evidence": {"error": str(error)},
        }
    return {
        **_check_result_base(effective_check),
        "status": result["status"],
        "evidence": result["evidence"],
    }


def _execute_runtime_capability_check(
    effective_check: EffectiveCheck,
) -> dict[str, object]:
    return {
        **_check_result_base(effective_check),
        "status": "passed",
        "evidence": {
            "reason": "runtime capability check passed during planning",
        },
    }


def _execute_agent_prompt_check(
    effective_check: EffectiveCheck,
    instance: RuntimeInstance,
    agent_prompt_runner: AgentPromptRunner | None,
) -> dict[str, object]:
    check = effective_check.check
    if agent_prompt_runner is None:
        return {
            **_check_result_base(effective_check),
            "status": "error",
            "evidence": {
                "prompt": check.prompt or "",
                "tool_calls": [],
                "error": "agent prompt runner not configured",
            },
        }

    prompt = _agent_prompt_text(check.prompt or "", instance.workspace_path)
    result = agent_prompt_runner(
        prompt,
        instance.env,
        instance.workspace_path,
    )
    response_contract = _agent_response_contract(result.response)
    missing_tool_calls = [
        name for name in check.expect_tool_calls if name not in result.tool_calls
    ]
    evidence: dict[str, object] = {
        "prompt": prompt,
        "exit_code": result.exit_code,
        "response": result.response,
        "expected_tool_calls": list(check.expect_tool_calls),
        "tool_calls": list(result.tool_calls),
    }
    if response_contract.response_json is not None:
        evidence["response_json"] = response_contract.response_json
    if result.transcript_path is not None:
        evidence["transcript_path"] = str(result.transcript_path)
    if response_contract.errors:
        evidence["response_contract_errors"] = response_contract.errors
    if missing_tool_calls:
        evidence["missing_tool_calls"] = missing_tool_calls
    status = (
        "passed"
        if result.exit_code == 0
        and not missing_tool_calls
        and not response_contract.errors
        else "failed"
    )
    return {
        **_check_result_base(effective_check),
        "status": status,
        "evidence": evidence,
    }


def _agent_prompt_text(prompt: str, cwd: Path) -> str:
    prompt_path = Path(prompt)
    if not prompt_path.is_absolute():
        prompt_path = cwd / prompt_path
    if prompt_path.is_file():
        return prompt_path.read_text(encoding="utf-8")
    return prompt


def _check_result_base(effective_check: EffectiveCheck) -> dict[str, object]:
    check = effective_check.check
    return {
        "name": check.name,
        "kind": check.kind,
        "origin": effective_check.origin,
        "origin_name": effective_check.origin_name,
        "required": effective_check.required,
    }


@dataclass(frozen=True)
class AgentResponseContract:
    response_json: dict[str, object] | None
    errors: list[str]


def _agent_response_contract(response: str) -> AgentResponseContract:
    payload = parse_agent_response_json(response)
    if payload is None:
        return AgentResponseContract(
            response_json=None,
            errors=["response must be a JSON object"],
        )

    errors = []
    if payload.get("available") is not True:
        errors.append("response.available must be true")
    if payload.get("configured") is not True:
        errors.append("response.configured must be true")
    return AgentResponseContract(response_json=payload, errors=errors)


def parse_agent_response_json(response: str) -> dict[str, object] | None:
    for candidate in (
        response,
        _markdown_fenced_body(response),
        *_fenced_bodies(response),
    ):
        if candidate is None:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _markdown_fenced_body(response: str) -> str | None:
    lines = response.strip().splitlines()
    if len(lines) < 3:
        return None
    if not lines[0].startswith("```") or lines[-1] != "```":
        return None
    return "\n".join(lines[1:-1])


def _fenced_bodies(response: str) -> list[str]:
    bodies = []
    lines = response.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].startswith("```"):
            index += 1
            continue
        start = index + 1
        index = start
        while index < len(lines) and lines[index] != "```":
            index += 1
        if index < len(lines):
            bodies.append("\n".join(lines[start:index]))
        index += 1
    return bodies


def _is_under(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _isolation_root(instance: RuntimeInstance) -> Path:
    if instance.runtime.backend == "container":
        return Path(instance.env["HOME"])
    return instance.temp_home


def _artifact_status(checks: list[dict[str, object]]) -> str:
    for check in checks:
        if check["required"] and check["status"] != "passed":
            return "failed"
    return "passed"


def _required_secret_names(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> tuple[str, ...]:
    names = list(runtime.required_secrets)
    for rigging in riggings:
        names.extend(rigging.required_secrets)
    return tuple(dict.fromkeys(names))


def _secret_ref_to_json(name: str, secret: SecretReference) -> dict[str, object]:
    ref = secret.name if secret.source == "env" else secret.path
    return {
        "name": name,
        "source": secret.source,
        "ref": ref,
        "redacted": True,
    }
