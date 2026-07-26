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
