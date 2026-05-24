from __future__ import annotations

import os


def subprocess_env(
    argv: tuple[str, ...],
    runtime_env: dict[str, str],
) -> dict[str, str]:
    env = dict(os.environ)
    env.update(runtime_env)
    if _uses_docker(argv) and "PATH" in os.environ:
        env["PATH"] = os.environ["PATH"]
    return env


def _uses_docker(argv: tuple[str, ...]) -> bool:
    return bool(argv) and argv[0] == "docker"
