from __future__ import annotations

from typing import Any

from yacht.regatta import CourseAdapter, Regatta, RiggingRecipe, RuntimeRecipe


def regatta_surfaces_to_json(regatta: Regatta) -> dict[str, Any]:
    runtimes = _configured_vessel_runtimes(regatta)
    riggings = _configured_vessel_riggings(regatta)
    payload: dict[str, Any] = {
        "agent_harnesses": sorted(
            {agent for runtime in runtimes if (agent := agent_for_runtime(runtime))}
        ),
        "tools": sorted({tool for rigging in riggings for tool in rigging.tools}),
    }
    if regatta.course.adapter is not None:
        payload["benchmark"] = benchmark_surface_to_json(
            regatta.course.name,
            regatta.course.adapter,
        )
    return payload


def _configured_vessel_runtimes(regatta: Regatta) -> list[RuntimeRecipe]:
    runtimes: list[RuntimeRecipe] = []
    for vessel in regatta.vessels:
        if vessel.runtime is None:
            continue
        runtime = regatta.runtime_recipes.get(vessel.runtime)
        if runtime is not None:
            runtimes.append(runtime)
    return runtimes


def _configured_vessel_riggings(regatta: Regatta) -> list[RiggingRecipe]:
    riggings: list[RiggingRecipe] = []
    for vessel in regatta.vessels:
        for rigging_name in vessel.rigging:
            rigging = regatta.rigging_recipes.get(rigging_name)
            if rigging is not None:
                riggings.append(rigging)
    return riggings


def vessel_surfaces_to_json(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    agent = agent_for_runtime(runtime)
    if agent is not None:
        payload["agent_harness"] = agent
    tools = sorted({tool for rigging in riggings for tool in rigging.tools})
    if tools:
        payload["tools"] = tools
    return payload


def benchmark_surface_to_json(name: str, adapter: CourseAdapter) -> dict[str, str]:
    return {
        "name": name,
        "adapter": adapter.kind,
        "dataset": adapter.dataset,
        "split": adapter.split,
        "execution_harness": adapter.harness,
    }


def agent_for_runtime(runtime: RuntimeRecipe) -> str | None:
    if runtime.agent is not None:
        return runtime.agent
    if runtime.command:
        return runtime.command[0]
    return None
