"""Resolve the active local Unix Docker socket for orchestrator bind mounts."""

from __future__ import annotations

import os
import subprocess

from yacht.domain.model import ConfigError

_INTERNAL_SOCKET = "/var/run/docker.sock"


def docker_socket_bind_spec() -> str:
    context = os.environ.get("DOCKER_CONTEXT") or None
    host = os.environ.get("DOCKER_HOST") or None
    if context is not None:
        endpoint = _inspect_context_host(context)
    elif host is not None:
        endpoint = host
    else:
        endpoint = _inspect_context_host(None)
    return f"{_local_unix_socket_path(endpoint)}:{_INTERNAL_SOCKET}"


def _inspect_context_host(context_name: str | None) -> str:
    argv = ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
    if context_name is not None:
        argv.append(context_name)
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise ConfigError("docker CLI not found on PATH") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or "no output"
        target = context_name or "the current context"
        raise ConfigError(f"docker context inspect failed for {target}: {detail}")
    host = completed.stdout.strip()
    if not host:
        target = context_name or "the current context"
        raise ConfigError(f"docker context inspect returned no Host for {target}")
    return host


def _local_unix_socket_path(endpoint: str) -> str:
    unix_prefix = "unix://"
    if not endpoint.startswith(unix_prefix):
        raise ConfigError(f"Docker endpoint {endpoint} is not a local Unix socket")
    path = endpoint.removeprefix(unix_prefix)
    if not path.startswith("/") or any(char in path for char in ":?#"):
        raise ConfigError(f"Docker endpoint {endpoint} is not a local Unix socket")
    return path
