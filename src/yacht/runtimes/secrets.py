from __future__ import annotations

from collections.abc import Mapping

from yacht.domain.model import Regatta, RiggingRecipe, RuntimeRecipe


def required_secret_names(
    runtime: RuntimeRecipe,
    riggings: tuple[RiggingRecipe, ...],
) -> tuple[str, ...]:
    names = list(runtime.required_secrets)
    for rigging in riggings:
        names.extend(rigging.required_secrets)
    return tuple(dict.fromkeys(names))


def secret_env_by_vessel(
    regatta: Regatta,
    secret_values: Mapping[str, str],
) -> dict[str, dict[str, str]]:
    """Env-var name -> value per vessel, for env-source required secrets.

    Yacht scrubs every ``@env:`` source variable from its own environment
    once it is resolved (see :mod:`yacht.secret_resolution`), so a native
    launcher that forwards a variable by name (``docker run -e NAME``)
    needs it reintroduced explicitly. Only the secrets a vessel's runtime
    and rigging actually declare are reintroduced, and only when a value
    was supplied.
    """
    per_vessel: dict[str, dict[str, str]] = {}
    for vessel in regatta.vessels:
        if vessel.runtime is None:
            continue
        runtime = regatta.runtime_recipes.get(vessel.runtime)
        if runtime is None:
            continue
        riggings = tuple(
            regatta.rigging_recipes[name]
            for name in vessel.rigging
            if name in regatta.rigging_recipes
        )
        env: dict[str, str] = {}
        for secret_name in required_secret_names(runtime, riggings):
            secret = regatta.secrets.get(secret_name)
            if secret is None or secret.source != "env" or secret.name is None:
                continue
            if secret_name not in secret_values:
                continue
            env[secret.name] = secret_values[secret_name]
        if env:
            per_vessel[vessel.name] = env
    return per_vessel
