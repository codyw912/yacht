from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from typing import Protocol

from yacht.domain.model import ConfigError, InstanceSelection


SELECTION_ALGORITHM = "sha256-rank-v1"
MAX_SELECTION_SEED = (1 << 63) - 1
_RANK_DOMAIN = "yacht.instance-selection.rank.v1"
_POPULATION_DOMAIN = "yacht.instance-selection.population.v1"
_LENGTH_BYTES = 8


class _Hash(Protocol):
    def update(self, data: bytes, /) -> None: ...


def select_random_instances(
    instance_ids: Iterable[str],
    *,
    max_instances: int,
    seed: object,
) -> tuple[tuple[str, ...], InstanceSelection]:
    population = _validated_population(instance_ids)
    if not isinstance(max_instances, int) or isinstance(max_instances, bool):
        raise ConfigError("random selection max_instances must be an integer")
    if max_instances < 1:
        raise ConfigError("random selection max_instances must be at least 1")
    if max_instances > len(population):
        raise ConfigError(
            "random selection max_instances must not exceed the population size "
            f"of {len(population)}"
        )
    validated_seed = _validated_seed(seed)

    selected = tuple(
        instance_id
        for _, _, instance_id in sorted(
            (
                (
                    _instance_rank(instance_id, seed=validated_seed),
                    instance_id.encode("utf-8"),
                    instance_id,
                )
                for instance_id in population
            )
        )[:max_instances]
    )
    provenance = InstanceSelection(
        method="random",
        algorithm=SELECTION_ALGORITHM,
        seed=validated_seed,
        requested_instances=max_instances,
        population_count=len(population),
        population_digest=_instance_population_digest(population),
    )
    return selected, provenance


def instance_rank(instance_id: str, *, seed: int) -> bytes:
    return _instance_rank(instance_id, seed=_validated_seed(seed))


def instance_population_digest(instance_ids: Iterable[str]) -> str:
    return _instance_population_digest(_validated_population(instance_ids))


def _instance_rank(instance_id: str, *, seed: int) -> bytes:
    digest = sha256()
    _update_text_field(digest, _RANK_DOMAIN)
    _update_text_field(digest, str(seed))
    _update_text_field(digest, instance_id)
    return digest.digest()


def _instance_population_digest(population: tuple[str, ...]) -> str:
    digest = sha256()
    _update_text_field(digest, _POPULATION_DOMAIN)
    _update_text_field(digest, str(len(population)))
    for instance_id in sorted(population, key=lambda value: value.encode("utf-8")):
        _update_text_field(digest, instance_id)
    return f"sha256:{digest.hexdigest()}"


def _validated_population(instance_ids: Iterable[str]) -> tuple[str, ...]:
    population = tuple(instance_ids)
    if not population:
        raise ConfigError("random selection requires at least one instance ID")
    seen: set[str] = set()
    for index, instance_id in enumerate(population):
        if not isinstance(instance_id, str) or not instance_id:
            raise ConfigError(
                f"random selection instance_ids[{index}] must be a non-empty string"
            )
        if instance_id in seen:
            raise ConfigError(f"random selection instance_ids[{index}] is duplicated")
        seen.add(instance_id)
    return population


def _validated_seed(seed: object) -> int:
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ConfigError("random selection seed must be an integer")
    if seed < 0 or seed > MAX_SELECTION_SEED:
        raise ConfigError(
            f"random selection seed must be between 0 and {MAX_SELECTION_SEED}"
        )
    return seed


def _update_text_field(digest: _Hash, value: str) -> None:
    encoded = value.encode("utf-8")
    digest.update(len(encoded).to_bytes(_LENGTH_BYTES, "big"))
    digest.update(encoded)
