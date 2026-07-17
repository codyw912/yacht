"""Hierarchical provenance facets over vessel records (ADR 0009/0010).

Facet values are derived from a record's collapsed provenance block. The
hierarchy is expressed by facet key: `harness` matches on name alone while
`harness.version` matches the qualified name-plus-version, so "all runs of
claude-code" and "only claude-code 2.1.211" are the same query at
different depths. A leaf that collapsed to null (unresolvable or mixed)
yields no facet value: it lands in the "unknown" group and never matches a
value filter — a mixed-provenance record cannot satisfy a version-exact
query by accident.
"""

from __future__ import annotations

from typing import Any

from yacht.serve.collection import VesselRecord
from yacht.domain.model import ConfigError


FACET_KEYS = (
    "harness",
    "harness.version",
    "model",
    "model.resolved",
    "backend",
    "image",
    "tool",
    "tool.version",
)

UNKNOWN_GROUP = "unknown"


def record_facets(record: VesselRecord) -> dict[str, tuple[str, ...]]:
    """Facet values for one record; multi-valued keys may carry several."""
    provenance = record.provenance or {}
    harness = _section(provenance, "harness")
    model = _section(provenance, "model")
    runtime = _section(provenance, "runtime")
    tools = provenance.get("tools") or []
    facets: dict[str, tuple[str, ...]] = {
        "harness": _single(harness.get("name")),
        "harness.version": _qualified(harness.get("name"), harness.get("version")),
        "model": _single(model.get("configured")),
        "model.resolved": _single(model.get("resolved")),
        "backend": _single(runtime.get("backend")),
        "image": _single(runtime.get("image")),
        "tool": tuple(
            str(tool["name"])
            for tool in tools
            if isinstance(tool, dict) and tool.get("name")
        ),
        "tool.version": tuple(
            f"{tool['name']}@{tool['version']}"
            for tool in tools
            if isinstance(tool, dict) and tool.get("name") and tool.get("version")
        ),
    }
    return facets


def filter_records(
    records: list[VesselRecord],
    filters: dict[str, str],
) -> list[VesselRecord]:
    for key in filters:
        _require_facet_key(key)
    return [
        record
        for record in records
        if all(value in record_facets(record)[key] for key, value in filters.items())
    ]


def group_records(
    records: list[VesselRecord],
    key: str,
) -> dict[str, list[VesselRecord]]:
    """Group records by facet value; multi-valued records join every group.

    Records with no value for the facet land under UNKNOWN_GROUP so a
    grouped view always accounts for every record it was given.
    """
    _require_facet_key(key)
    groups: dict[str, list[VesselRecord]] = {}
    for record in records:
        values = record_facets(record)[key] or (UNKNOWN_GROUP,)
        for value in values:
            groups.setdefault(value, []).append(record)
    return dict(sorted(groups.items(), key=_unknown_last))


def facet_values(
    records: list[VesselRecord],
    key: str,
) -> list[tuple[str, int]]:
    """Distinct values for a facet with record counts, for rendering pickers."""
    return [
        (value, len(group))
        for value, group in group_records(records, key).items()
        if value != UNKNOWN_GROUP
    ]


def _require_facet_key(key: str) -> None:
    if key not in FACET_KEYS:
        raise ConfigError(
            f"unsupported provenance facet {key}; supported: " + ", ".join(FACET_KEYS)
        )


def _single(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) and value:
        return (value,)
    return ()


def _qualified(name: Any, version: Any) -> tuple[str, ...]:
    if not (isinstance(name, str) and name):
        return ()
    if not (isinstance(version, str) and version):
        return ()
    return (f"{name} {version}",)


def _section(provenance: dict[str, Any], key: str) -> dict[str, Any]:
    value = provenance.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _unknown_last(item: tuple[str, list[VesselRecord]]) -> tuple[int, str]:
    value, _ = item
    return (1 if value == UNKNOWN_GROUP else 0, value)
