"""Pure helpers for the declared-harness Harbor agent (ADR 0016).

No harbor imports here: this module is unit-tested from the yacht repo
without the harbor package installed, mirroring rigging.py.
"""

from __future__ import annotations

import hashlib
import shlex
from pathlib import Path
from typing import Any


CONTAINER_BINARY_DIR = "/installed-agent/bin"
CONTAINER_EVIDENCE_PATH = "/logs/agent/harness-evidence.json"
EVIDENCE_SCHEMA = "yacht.harness-evidence.v1"


class DeclaredAgentError(RuntimeError):
    pass


def verify_artifact(path: Path, sha256: str) -> None:
    if not path.is_file():
        raise DeclaredAgentError(f"harness install artifact not found: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != sha256:
        raise DeclaredAgentError(
            f"harness install artifact {path} does not match its pinned "
            f"sha256 (expected {sha256}, found {digest})"
        )


def binary_path(declaration: dict[str, Any]) -> str:
    return f"{CONTAINER_BINARY_DIR}/{declaration['name']}"


def install_commands(declaration: dict[str, Any]) -> list[str]:
    """Commands run in the task container after the artifact upload."""
    binary = binary_path(declaration)
    sha256 = str(declaration["install"]["sha256"])
    return [
        f"sha256sum {shlex.quote(binary)} | grep -q {shlex.quote(sha256)}",
        f"chmod 0755 {shlex.quote(binary)}",
    ]


def run_command(
    declaration: dict[str, Any],
    *,
    model: str,
    instruction: str,
) -> str:
    """Shell command string that runs the declared harness in-container."""
    argv = [
        item.replace("{model}", model) for item in declaration.get("command", [])
    ]
    if not argv:
        raise DeclaredAgentError(
            f"declared harness {declaration.get('name')} has no command; "
            "harbor courses require the declaration to set one"
        )
    argv[0] = binary_path(declaration) if argv[0] == declaration["name"] else argv[0]
    quoted = " ".join(shlex.quote(item) for item in argv)
    env_prefix = f"YACHT_EVIDENCE_PATH={shlex.quote(CONTAINER_EVIDENCE_PATH)} "
    if declaration.get("prompt", "argument") == "stdin":
        return (
            f"mkdir -p /logs/agent && printf %s {shlex.quote(instruction)} | "
            f"{env_prefix}{quoted}"
        )
    return f"mkdir -p /logs/agent && {env_prefix}{quoted} {shlex.quote(instruction)}"


def validate_evidence(payload: Any) -> dict[str, Any]:
    """Minimal in-launcher validation of the evidence contract.

    The full validator lives in yacht's schema module; the launcher
    checks the fields it maps into the trial result.
    """
    if not isinstance(payload, dict):
        raise DeclaredAgentError("harness evidence must be a JSON object")
    if payload.get("schema") != EVIDENCE_SCHEMA:
        raise DeclaredAgentError(
            f"harness evidence schema must be {EVIDENCE_SCHEMA}"
        )
    if not isinstance(payload.get("response"), str):
        raise DeclaredAgentError("harness evidence response must be a string")
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise DeclaredAgentError("harness evidence usage must be an object")
    for key in ("input_tokens", "output_tokens"):
        value = usage.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise DeclaredAgentError(
                f"harness evidence usage.{key} must be an integer >= 0"
            )
    return payload


def context_fields(evidence: dict[str, Any]) -> dict[str, int | float | None]:
    usage = evidence["usage"]
    cache_tokens = usage.get("cache_read_tokens")
    cost = evidence.get("cost")
    cost_usd = None
    if isinstance(cost, dict):
        total = cost.get("total_usd")
        if isinstance(total, int | float) and not isinstance(total, bool):
            cost_usd = float(total)
    return {
        "n_input_tokens": int(usage["input_tokens"]),
        "n_output_tokens": int(usage["output_tokens"]),
        "n_cache_tokens": int(cache_tokens)
        if isinstance(cache_tokens, int) and not isinstance(cache_tokens, bool)
        else 0,
        "cost_usd": cost_usd,
    }


def normalize_evidence(declaration: dict[str, Any], payload: Any) -> dict[str, Any]:
    """Apply the declaration's evidence_map (if any), then validate.

    Twin of yacht.harnesses.evidence_map.map_native_evidence; keep
    semantics aligned.
    """
    mapping = declaration.get("evidence_map")
    if isinstance(mapping, dict) and mapping:
        payload = _map_native(mapping, payload)
    return validate_evidence(payload)


def _map_native(mapping: dict[str, Any], payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DeclaredAgentError("harness native output must be a JSON object")
    response = _mapped(payload, str(mapping["response"]), "response")
    if not isinstance(response, str):
        raise DeclaredAgentError("mapped response must be a string")
    usage: dict[str, Any] = {}
    for key in ("input_tokens", "output_tokens"):
        value = _mapped(payload, str(mapping[key]), key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise DeclaredAgentError(f"mapped {key} must be an integer >= 0")
        usage[key] = value
    document: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        "response": response,
        "usage": usage,
    }
    if "usage_reported" in mapping:
        reported = _mapped(payload, str(mapping["usage_reported"]), "usage_reported")
        if not isinstance(reported, bool):
            raise DeclaredAgentError("mapped usage_reported must be a boolean")
        usage["reported"] = reported
    if "tool_calls" in mapping:
        value = _mapped(payload, str(mapping["tool_calls"]), "tool_calls")
        if not isinstance(value, list):
            raise DeclaredAgentError("mapped tool_calls must be a list")
        calls = []
        for entry in value:
            if isinstance(entry, str) and entry:
                calls.append({"name": entry, "count": 1})
            elif (
                isinstance(entry, dict)
                and isinstance(entry.get("name"), str)
                and isinstance(entry.get("count"), int)
                and not isinstance(entry.get("count"), bool)
                and entry["count"] >= 1
            ):
                calls.append({"name": entry["name"], "count": entry["count"]})
            else:
                raise DeclaredAgentError(
                    "mapped tool_calls entries must be names or {name, count}"
                )
        document["tool_calls"] = calls
    if "model" in mapping:
        model = _mapped(payload, str(mapping["model"]), "model")
        if not isinstance(model, str) or not model:
            raise DeclaredAgentError("mapped model must be a non-empty string")
        document["model"] = model
    if "cost_usd" in mapping:
        cost = _mapped(payload, str(mapping["cost_usd"]), "cost_usd")
        if not isinstance(cost, int | float) or isinstance(cost, bool) or cost < 0:
            raise DeclaredAgentError("mapped cost_usd must be a number >= 0")
        document["cost"] = {"total_usd": float(cost)}
    return document


def _mapped(payload: dict[str, Any], path: str, field: str) -> Any:
    node: Any = payload
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise DeclaredAgentError(
                f"harness native output is missing mapped {field} path {path}"
            )
        node = node[part]
    return node
