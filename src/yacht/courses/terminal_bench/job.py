from __future__ import annotations

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
    "claude-code": "claude-code",
    "pi": "pi",
}

SUPPORTED_RIGGING_INSTALL_METHODS = ("mcp-server",)


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

    return {
        "schema": TERMINAL_BENCH_JOB_SCHEMA,
        "dataset": {
            "name": str(regatta.course.adapter.dataset),
            "version": str(regatta.course.adapter.split),
        },
        "tasks": [str(task.id) for task in regatta.course.tasks],
        "agent": {
            "name": _harbor_agent(runtime),
            "version": _harness_version(runtime),
            "model": str(vessel.model),
            "env": _agent_env(riggings),
            "mcp_servers": _mcp_servers(riggings),
        },
        "secret_env": _secret_env(regatta, runtime, riggings),
        "vessel": vessel.name,
    }


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


def _harbor_agent(runtime: RuntimeRecipe) -> str:
    harness = runtime.harness
    if harness is None:
        raise ConfigError(
            f"runtime {runtime.name} must declare a harness for terminal-bench"
        )
    agent = HARBOR_AGENT_BY_HARNESS.get(harness)
    if agent is None:
        supported = ", ".join(sorted(HARBOR_AGENT_BY_HARNESS))
        raise ConfigError(
            f"terminal-bench does not support harness {harness} yet; "
            f"supported harnesses: {supported}"
        )
    return agent


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
            if step.method != "mcp-server":
                supported = ", ".join(SUPPORTED_RIGGING_INSTALL_METHODS)
                raise ConfigError(
                    f"rigging {rigging.name} install method {step.method} is not "
                    f"supported for terminal-bench yet; supported methods: "
                    f"{supported}"
                )
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
