"""Structured run provenance extracted from existing evidence (ADR 0009).

Provenance states what is known about the setup that produced an artifact
and where each fact came from. Values are resolved only from evidence the
run already produces — the runtime image tag, the API-reported model id in
machine evidence, and pinned install targets. Anything that cannot be
resolved is recorded as null, never guessed.
"""

from __future__ import annotations

import json
import re
from typing import Any

from yacht import __version__
from yacht.domain.model import Regatta, RiggingRecipe, RuntimeInstance, Vessel
from yacht.reports.surface_metadata import harness_for_runtime


_IMAGE_TAG_VERSION = re.compile(r"(\d+(?:\.\d+)+)$")
_TARGET_VERSION = re.compile(r"^\d+(?:\.\d+)+(?:[-+][\w.-]+)?$")

PROVENANCE_LEAVES = (
    ("yacht", "version"),
    ("harness", "name"),
    ("harness", "version"),
    ("model", "configured"),
    ("model", "resolved"),
    ("runtime", "backend"),
    ("runtime", "image"),
)


def collapse_provenance(blocks: list[Any]) -> dict[str, Any] | None:
    """Collapse per-attempt or per-run provenance blocks into one summary.

    Leaves where every block agrees keep their value; leaves that disagree
    become null and are listed under "mixed" so an aggregate never presents
    blended provenance as homogeneous. Blocks that already carry a "mixed"
    list (earlier collapses) contribute it to the union. Returns None when
    no block carries provenance at all.
    """
    present = [block for block in blocks if isinstance(block, dict)]
    if not present:
        return None
    collapsed: dict[str, Any] = {
        "yacht": {},
        "harness": {},
        "model": {},
        "runtime": {},
    }
    mixed: set[str] = set()
    for block in present:
        inherited = block.get("mixed")
        if isinstance(inherited, list):
            mixed.update(str(item) for item in inherited)
    for section, leaf in PROVENANCE_LEAVES:
        values = {_leaf_value(block, section, leaf) for block in present}
        if len(values) == 1:
            collapsed[section][leaf] = values.pop()
        else:
            collapsed[section][leaf] = None
            mixed.add(f"{section}.{leaf}")
    tool_variants = {
        json.dumps(block.get("tools"), sort_keys=True) for block in present
    }
    if len(tool_variants) == 1:
        collapsed["tools"] = present[0].get("tools")
    else:
        collapsed["tools"] = None
        mixed.add("tools")
    collapsed["mixed"] = sorted(mixed)
    return collapsed


def _leaf_value(block: dict[str, Any], section: str, leaf: str) -> str | None:
    section_value = block.get(section)
    if not isinstance(section_value, dict):
        return None
    value = section_value.get(leaf)
    if isinstance(value, str) and value:
        return value
    return None


def build_provenance(
    *,
    regatta: Regatta,
    vessel: Vessel,
    instance: RuntimeInstance,
    machine_evidence: dict[str, Any],
) -> dict[str, Any]:
    runtime = instance.runtime
    return {
        "yacht": {"version": __version__},
        "harness": {
            "name": harness_for_runtime(runtime),
            "version": _observed_harness_version(machine_evidence)
            or runtime.harness_version
            or _harness_version_from_image(runtime.image),
        },
        "model": {
            "configured": vessel.model,
            "resolved": _resolved_model(machine_evidence),
        },
        "runtime": {
            "backend": runtime.backend,
            "image": runtime.image,
        },
        "tools": tool_provenance(regatta, vessel),
    }


def _harness_version_from_image(image: str | None) -> str | None:
    if image is None or ":" not in image:
        return None
    tag = image.rsplit(":", 1)[1]
    match = _IMAGE_TAG_VERSION.search(tag)
    if match is None:
        return None
    return match.group(1)


def _observed_harness_version(machine_evidence: dict[str, Any]) -> str | None:
    value = machine_evidence.get("harness_version")
    return value if isinstance(value, str) and value else None


def _resolved_model(machine_evidence: dict[str, Any]) -> str | None:
    model = machine_evidence.get("model")
    if isinstance(model, str) and model:
        return model
    return None


def tool_provenance(regatta: Regatta, vessel: Vessel) -> list[dict[str, Any]]:
    entries = []
    for rigging_name in vessel.rigging:
        rigging = regatta.rigging_recipes.get(rigging_name)
        if rigging is None:
            continue
        version, source = _rigging_version(rigging)
        entries.append(
            {
                "name": rigging.name,
                "tools": list(rigging.tools),
                "version": version,
                "source": source,
            }
        )
    return entries


def _rigging_version(rigging: RiggingRecipe) -> tuple[str | None, str | None]:
    """Resolve one unambiguous pinned version from the rigging's installs.

    Returns (None, None) when no install target carries a version, and also
    when several targets carry different versions — an ambiguous pin is not
    resolved, only recorded in the raw setup evidence.
    """
    pinned: list[tuple[str, str]] = []
    for step in rigging.install:
        version = _version_from_target(step.target)
        if version is not None:
            pinned.append((version, step.target))
    versions = {version for version, _ in pinned}
    if len(versions) != 1:
        return None, None
    version = versions.pop()
    sources = {target for _, target in pinned}
    return version, sources.pop() if len(sources) == 1 else None


def _version_from_target(target: str) -> str | None:
    if not target.startswith("npm:"):
        return None
    package = target.removeprefix("npm:")
    if "@" not in package.lstrip("@"):
        return None
    candidate = package.rsplit("@", 1)[1]
    if _TARGET_VERSION.fullmatch(candidate) is None:
        return None
    return candidate
