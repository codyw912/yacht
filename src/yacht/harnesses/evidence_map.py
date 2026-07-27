"""Map harness-native JSON output onto the evidence contract (ADR 0017).

A twin of this mapper lives in
containers/harbor-launcher/yacht_harbor_agents/declared_support.py for
the in-container path; keep their semantics aligned.
"""

from __future__ import annotations

from typing import Any

from yacht.contracts.schemas import HARNESS_EVIDENCE_SCHEMA, SchemaValidationError


REQUIRED_MAP_KEYS = ("response", "input_tokens", "output_tokens")
OPTIONAL_MAP_KEYS = ("tool_calls", "model", "cost_usd", "usage_reported")
ALLOWED_MAP_KEYS = frozenset(REQUIRED_MAP_KEYS + OPTIONAL_MAP_KEYS)


def map_native_evidence(
    evidence_map: dict[str, str],
    payload: Any,
) -> dict[str, Any]:
    """Build a normal-form evidence document from native harness JSON.

    Missing or wrong-typed mapped fields raise — the no-estimates
    policy applies to mappings exactly as to native emission.
    """
    if not isinstance(payload, dict):
        raise SchemaValidationError("harness native output must be a JSON object")
    response = _lookup(payload, evidence_map["response"], "response")
    if not isinstance(response, str):
        raise SchemaValidationError(
            f"mapped response ({evidence_map['response']}) must be a string"
        )
    usage: dict[str, Any] = {}
    for key in ("input_tokens", "output_tokens"):
        value = _lookup(payload, evidence_map[key], key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise SchemaValidationError(
                f"mapped {key} ({evidence_map[key]}) must be an integer >= 0"
            )
        usage[key] = value
    document: dict[str, Any] = {
        "schema": HARNESS_EVIDENCE_SCHEMA,
        "response": response,
        "usage": usage,
    }
    if "usage_reported" in evidence_map:
        reported = _lookup(payload, evidence_map["usage_reported"], "usage_reported")
        if not isinstance(reported, bool):
            raise SchemaValidationError(
                f"mapped usage_reported ({evidence_map['usage_reported']}) "
                "must be a boolean"
            )
        document["usage"]["reported"] = reported
    if "tool_calls" in evidence_map:
        document["tool_calls"] = _mapped_tool_calls(
            _lookup(payload, evidence_map["tool_calls"], "tool_calls")
        )
    if "model" in evidence_map:
        model = _lookup(payload, evidence_map["model"], "model")
        if not isinstance(model, str) or not model:
            raise SchemaValidationError(
                f"mapped model ({evidence_map['model']}) must be a non-empty string"
            )
        document["model"] = model
    if "cost_usd" in evidence_map:
        cost = _lookup(payload, evidence_map["cost_usd"], "cost_usd")
        if not isinstance(cost, int | float) or isinstance(cost, bool) or cost < 0:
            raise SchemaValidationError(
                f"mapped cost_usd ({evidence_map['cost_usd']}) must be a number >= 0"
            )
        document["cost"] = {"total_usd": float(cost)}
    return document


def _lookup(payload: dict[str, Any], path: str, field: str) -> Any:
    node: Any = payload
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise SchemaValidationError(
                f"harness native output is missing mapped {field} path {path}"
            )
        node = node[part]
    return node


def _mapped_tool_calls(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SchemaValidationError("mapped tool_calls must be a list")
    calls: list[dict[str, Any]] = []
    for entry in value:
        if isinstance(entry, str) and entry:
            calls.append({"name": entry, "count": 1})
        elif (
            isinstance(entry, dict)
            and isinstance(entry.get("name"), str)
            and entry["name"]
            and isinstance(entry.get("count"), int)
            and not isinstance(entry.get("count"), bool)
            and entry["count"] >= 1
        ):
            calls.append({"name": entry["name"], "count": entry["count"]})
        else:
            raise SchemaValidationError(
                "mapped tool_calls entries must be names or {name, count}"
            )
    return calls
