from __future__ import annotations

from pathlib import Path

from yacht.domain.model import ConfigError, Regatta, load_regatta
from yacht.reports.surface_metadata import regatta_surfaces_to_json


def configured_harness_name(
    config_path: Path,
    *,
    command_label: str = "real benchmark commands",
) -> str:
    regatta = load_regatta(config_path)
    return configured_harness_name_for_regatta(
        regatta,
        command_label=command_label,
    )


def configured_harness_name_for_regatta(
    regatta: Regatta,
    *,
    command_label: str,
) -> str:
    agents = tuple(regatta_surfaces_to_json(regatta).get("agent_harnesses", ()))
    if len(agents) == 1:
        return str(agents[0])
    if not agents:
        raise ConfigError(
            f"{command_label} require exactly one configured agent harness; found none"
        )
    raise ConfigError(
        f"{command_label} require exactly one configured agent harness; "
        f"found {', '.join(str(agent) for agent in agents)}"
    )


def configured_agent_name(config_path: Path) -> str:
    return configured_harness_name(config_path)
