"""Resolution of ``--secret`` arguments into an in-memory secret map.

Yacht accepts secrets as ``--secret NAME=VALUE`` or
``--secret NAME=@env:VARIABLE``. An ``@env:`` reference names a variable
that an outer tool (a SecretSpec scope, a CI runner, an operator's shell)
placed in Yacht's own environment.

Yacht's subprocess environments are built from the ambient environment
(:func:`yacht.runtimes.process.subprocess_env`), so a referenced variable
would otherwise be inherited by every helper process Yacht spawns —
harness installs, rigging setup, preflight probes — including those for
vessels that never declared the secret. Resolution therefore ends by
removing the referenced variable names from the ambient environment:

* each referenced variable is read exactly once, before any mutation;
* a parse or resolution failure raises before the environment is touched,
  so a failed invocation leaves the environment exactly as it found it;
* the values survive in :class:`ResolvedSecrets`, and Yacht reintroduces
  each one only into runtimes whose ``required_secrets`` declare the
  logical secret (``env_with_secret_values`` on each runtime resolution);
* several logical secrets may reference the same variable — each gets the
  value, and the variable is removed once.

Values are never logged, embedded in exceptions, written to artifacts, or
placed in command arguments; artifacts carry redacted references only.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping, MutableMapping, Sequence
from dataclasses import dataclass

from yacht.domain.model import ConfigError

ENV_REFERENCE_PREFIX = "@env:"


@dataclass(frozen=True)
class ResolvedSecrets(Mapping[str, str]):
    """Logical secret name -> value, plus the variables it consumed.

    ``blocked_env_names`` records the ambient variable names that were
    resolved and then removed, so callers and tests can assert what left
    the ambient environment without touching the values themselves.
    """

    values: Mapping[str, str]
    blocked_env_names: frozenset[str] = frozenset()

    def __getitem__(self, name: str) -> str:
        return self.values[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def __repr__(self) -> str:
        # Never render values: a repr reaches logs and test failure output.
        return (
            f"ResolvedSecrets(names={sorted(self.values)}, "
            f"blocked_env_names={sorted(self.blocked_env_names)})"
        )


def resolve_secret_arguments(
    values: list[str],
    *,
    environ: MutableMapping[str, str] | None = None,
) -> ResolvedSecrets:
    """Resolve ``NAME=VALUE`` / ``NAME=@env:VARIABLE`` arguments.

    Every referenced variable is removed from ``environ`` (defaulting to
    :data:`os.environ`) once all arguments resolve successfully.

    A logical name may appear more than once — the scoped wrappers append
    their own ``--secret`` after the caller's arguments. The last entry
    wins for the value, but *every* referenced variable is still read and
    removed: an overridden reference must not be left behind in the
    ambient environment.
    """
    source = os.environ if environ is None else environ
    entries = [_parse_entry(value) for value in values]
    referenced_names = tuple(
        dict.fromkeys(entry.env_name for entry in entries if entry.env_name is not None)
    )
    resolved_by_env_name = _read_referenced_variables(entries, source)

    secrets: dict[str, str] = {}
    for entry in entries:
        if entry.env_name is None:
            secrets[entry.name] = entry.literal
        else:
            secrets[entry.name] = resolved_by_env_name[entry.env_name]

    for env_name in referenced_names:
        source.pop(env_name, None)
    return ResolvedSecrets(
        values=secrets,
        blocked_env_names=frozenset(referenced_names),
    )


@dataclass(frozen=True)
class _SecretEntry:
    """One ``--secret`` argument: a literal value or an ``@env:`` reference."""

    name: str
    literal: str = ""
    env_name: str | None = None


def _parse_entry(value: str) -> _SecretEntry:
    if "=" not in value:
        raise ConfigError("secrets must use NAME=VALUE format")
    name, secret_value = value.split("=", maxsplit=1)
    if not name:
        raise ConfigError("secret names must be non-empty")
    if not secret_value:
        raise ConfigError(f"secret {name} must be non-empty")
    if not secret_value.startswith(ENV_REFERENCE_PREFIX):
        return _SecretEntry(name=name, literal=secret_value)
    env_name = secret_value.removeprefix(ENV_REFERENCE_PREFIX)
    if not env_name:
        raise ConfigError(f"secret {name} @env reference must name an env var")
    return _SecretEntry(name=name, env_name=env_name)


def _read_referenced_variables(
    entries: Sequence[_SecretEntry],
    source: Mapping[str, str],
) -> dict[str, str]:
    """Read each referenced variable exactly once, validating as we go."""
    resolved: dict[str, str] = {}
    for entry in entries:
        env_name = entry.env_name
        if env_name is None or env_name in resolved:
            continue
        if env_name not in source:
            raise ConfigError(
                f"environment variable {env_name} is not set for secret {entry.name}"
            )
        env_value = source[env_name]
        if not env_value:
            raise ConfigError(
                f"environment variable {env_name} is empty for secret {entry.name}"
            )
        resolved[env_name] = env_value
    return resolved
