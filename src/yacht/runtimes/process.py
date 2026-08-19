"""Subprocess environment construction for every command Yacht runs.

A child process inherits Yacht's ambient environment plus the runtime's
own env. Secrets are not part of the ambient environment: a ``@env:``
source variable is removed from it the moment Yacht resolves it (see
:mod:`yacht.secret_resolution`), and reappears only in the
``runtime_env`` of a runtime whose ``required_secrets`` declare it. A
helper subprocess for a vessel that declared no secret therefore cannot
inherit one.
"""

from __future__ import annotations

import os
from collections.abc import Mapping


def subprocess_env(
    argv: tuple[str, ...],
    runtime_env: Mapping[str, str],
) -> dict[str, str]:
    env = dict(os.environ)
    env.update(runtime_env)
    if _uses_docker(argv) and "PATH" in os.environ:
        env["PATH"] = os.environ["PATH"]
    return env


def _uses_docker(argv: tuple[str, ...]) -> bool:
    return bool(argv) and argv[0] == "docker"
