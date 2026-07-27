from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from yacht.domain.model import (
    ConfigError,
    Regatta,
    RiggingRecipe,
    RuntimeRecipe,
    Vessel,
)


TERMINAL_BENCH_JOB_SCHEMA = "yacht.terminal-bench-job.v1"
TERMINAL_BENCH_JOB_FILENAME = "terminal-bench-job.json"

HARBOR_AGENT_BY_HARNESS = {
    "claude-code": "yacht_harbor_agents.agents:YachtClaudeCode",
    "pi": "yacht_harbor_agents.agents:YachtPi",
}

SUPPORTED_RIGGING_INSTALL_METHODS = ("config-file", "mcp-server", "package")

_PACKAGE_PIN = re.compile(r"@\d+(?:\.\d+)+(?:[-+][\w.-]+)?$")


def render_terminal_bench_job(
    *,
    regatta: Regatta,
    vessel_name: str,
) -> dict[str, Any]:
    if regatta.course.adapter is None:
        raise ConfigError("terminal-bench job requires course.adapter")
    vessel = _vessel(regatta, vessel_name)
    runtime = _runtime(regatta, vessel)
    riggings = [_rigging(regatta, vessel, name) for name in vessel.rigging]

    agent: dict[str, Any] = {
        "name": _harness_name(runtime),
        "import_path": _harbor_agent(regatta, runtime),
        "version": _harness_version(runtime),
        "model": str(vessel.model),
        "env": _agent_env(riggings),
        "mcp_servers": _mcp_servers(riggings),
        "rigging_steps": _rigging_steps(riggings),
    }
    declaration = _declaration_payload(regatta, runtime)
    if declaration is not None:
        agent["declaration"] = declaration
    return {
        "schema": TERMINAL_BENCH_JOB_SCHEMA,
        "dataset": _dataset(regatta.course.adapter),
        "tasks": [str(task.id) for task in regatta.course.tasks],
        "agent": agent,
        "launcher_image": _launcher_image(runtime),
        "secret_env": _secret_env(regatta, runtime, riggings),
        "vessel": vessel.name,
    }


def _dataset(adapter: Any) -> dict[str, str]:
    if adapter.kind == "custom-eval":
        from yacht.courses.task_directory import task_directory_digest

        path = Path(str(adapter.dataset))
        return {
            "path": str(path),
            "digest": task_directory_digest(path),
        }
    return {
        "name": str(adapter.dataset),
        "version": str(adapter.split),
    }


def _launcher_image(runtime: RuntimeRecipe) -> str:
    if runtime.image is None:
        raise ConfigError(
            f"runtime {runtime.name} must declare the harbor launcher image"
        )
    return str(runtime.image)


def _vessel(regatta: Regatta, vessel_name: str) -> Vessel:
    for vessel in regatta.vessels:
        if vessel.name == vessel_name:
            return vessel
    raise ConfigError(f"vessel {vessel_name} is not defined in the regatta config")


def _runtime(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise ConfigError(
            f"vessel {vessel.name} must declare a runtime for terminal-bench"
        )
    runtime = regatta.runtime_recipes.get(vessel.runtime)
    if runtime is None:
        raise ConfigError(
            f"vessel {vessel.name} references undefined runtime {vessel.runtime}"
        )
    return runtime


def _rigging(regatta: Regatta, vessel: Vessel, rigging_name: str) -> RiggingRecipe:
    rigging = regatta.rigging_recipes.get(rigging_name)
    if rigging is None:
        raise ConfigError(
            f"vessel {vessel.name} references undefined rigging {rigging_name}"
        )
    return rigging


def _harness_name(runtime: RuntimeRecipe) -> str:
    harness = runtime.harness
    if harness is None:
        raise ConfigError(
            f"runtime {runtime.name} must declare a harness for terminal-bench"
        )
    return harness


def _harbor_agent(regatta: Regatta, runtime: RuntimeRecipe) -> str:
    harness = _harness_name(runtime)
    agent = HARBOR_AGENT_BY_HARNESS.get(harness)
    if agent is not None:
        return agent
    if harness in regatta.harness_declarations:
        return "yacht_harbor_agents.agents:YachtDeclared"
    supported = ", ".join(sorted(HARBOR_AGENT_BY_HARNESS))
    raise ConfigError(
        f"terminal-bench does not support harness {harness} yet; "
        f"supported harnesses: {supported}, or a harness declared in the "
        "config"
    )


def _declaration_payload(
    regatta: Regatta,
    runtime: RuntimeRecipe,
) -> dict[str, Any] | None:
    harness = _harness_name(runtime)
    if harness in HARBOR_AGENT_BY_HARNESS:
        return None
    declaration = regatta.harness_declarations.get(harness)
    if declaration is None:
        return None
    if not declaration.command:
        raise ConfigError(
            f"declared harness {harness} must set command to run on a harbor course"
        )
    if declaration.install is None:
        raise ConfigError(
            f"declared harness {harness} must set a pinned install "
            "(url or path + sha256) to run on a harbor course"
        )
    install: dict[str, str] = {"sha256": declaration.install.sha256}
    if declaration.install.url is not None:
        install["url"] = declaration.install.url
    if declaration.install.path is not None:
        install["path"] = declaration.install.path
    payload = {
        "name": declaration.name,
        "prompt": declaration.prompt,
        "evidence": declaration.evidence,
        "command": list(declaration.command),
        "install": install,
    }
    if declaration.evidence_map:
        payload["evidence_map"] = dict(declaration.evidence_map)
    return payload


def _harness_version(runtime: RuntimeRecipe) -> str:
    if runtime.harness_version is None:
        raise ConfigError(
            f"runtime {runtime.name} must pin harness_version for terminal-bench"
        )
    return str(runtime.harness_version)


def _secret_env(
    regatta: Regatta,
    runtime: RuntimeRecipe,
    riggings: list[RiggingRecipe],
) -> list[str]:
    names = list(runtime.required_secrets)
    for rigging in riggings:
        names.extend(rigging.required_secrets)
    env_names = []
    for name in dict.fromkeys(names):
        secret = regatta.secrets.get(name)
        if secret is None:
            raise ConfigError(f"required secret {name} is not defined in the config")
        if secret.source != "env" or secret.name is None:
            raise ConfigError(
                f"terminal-bench supports env-source secrets only; "
                f"secret {name} uses source {secret.source}"
            )
        env_names.append(secret.name)
    return env_names


def _agent_env(riggings: list[RiggingRecipe]) -> dict[str, str]:
    env: dict[str, str] = {}
    for rigging in riggings:
        for key, value in rigging.env.items():
            if key in env and env[key] != value:
                raise ConfigError(
                    f"rigging {rigging.name} sets conflicting env value for {key}"
                )
            env[key] = value
    return env


def _mcp_servers(riggings: list[RiggingRecipe]) -> list[dict[str, Any]]:
    servers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rigging in riggings:
        for step in rigging.install:
            _require_supported_method(rigging, step)
            if step.method != "mcp-server":
                continue
            if not step.command:
                raise ConfigError(
                    f"rigging {rigging.name} mcp-server {step.target} must declare "
                    "a command"
                )
            if step.target in seen:
                raise ConfigError(
                    f"rigging {rigging.name} declares duplicate mcp-server "
                    f"{step.target}"
                )
            seen.add(step.target)
            servers.append(
                {
                    "name": str(step.target),
                    "command": str(step.command[0]),
                    "args": [str(item) for item in step.command[1:]],
                }
            )
    return servers


def _rigging_steps(riggings: list[RiggingRecipe]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for rigging in riggings:
        for step in rigging.install:
            _require_supported_method(rigging, step)
            if step.method == "mcp-server":
                continue
            if step.method == "package" and not _PACKAGE_PIN.search(step.target):
                raise ConfigError(
                    f"rigging {rigging.name} package {step.target} must pin a "
                    "version for terminal-bench"
                )
            steps.append(step.to_json())
    return steps


def _require_supported_method(
    rigging: RiggingRecipe,
    step: Any,
) -> None:
    if step.method not in SUPPORTED_RIGGING_INSTALL_METHODS:
        supported = ", ".join(SUPPORTED_RIGGING_INSTALL_METHODS)
        raise ConfigError(
            f"rigging {rigging.name} install method {step.method} is not "
            f"supported for terminal-bench yet; supported methods: "
            f"{supported}"
        )
