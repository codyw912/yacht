"""Harbor 0.20.0 Docker/Linux duplex compose transport helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from yacht_harbor_agents.rigging import OMP_PACKAGE


PINNED_HARBOR_VERSION = "0.20.0"
MAIN_SERVICE = "main"
DRIVER_FILENAME = "omp_control.ts"


class DuplexError(RuntimeError):
    pass


class UnsafeMountError(DuplexError):
    pass


def sanitize_compose_project_name(name: str) -> str:
    name = name.lower()
    if not re.match(r"^[a-z0-9]", name):
        name = "0" + name
    return re.sub(r"[^a-z0-9_-]", "-", name)


def build_compose_exec_argv(
    *,
    session_id: str,
    environment_dir: Path,
    compose_paths: list[Path],
    command: str,
    workdir: str | None,
    user: str | int | None,
    env: dict[str, str] | None,
) -> list[str]:
    argv = [
        "docker",
        "compose",
        "--project-name",
        sanitize_compose_project_name(session_id),
        "--project-directory",
        str(Path(environment_dir).resolve()),
    ]
    for path in compose_paths:
        argv.extend(["-f", str(Path(path).resolve())])
    argv.extend(["exec", "-T"])
    if workdir:
        argv.extend(["-w", workdir])
    if env:
        for key, value in env.items():
            argv.extend(["-e", f"{key}={value}"])
    if user is not None:
        argv.extend(["-u", str(user)])
    argv.append(MAIN_SERVICE)
    argv.extend(["bash", "-c", command])
    return argv


def require_harbor_docker_linux(
    environment: Any, harbor_version: str | None = None
) -> None:
    version = harbor_version
    if version is None:
        import importlib.metadata

        try:
            version = importlib.metadata.version("harbor")
        except importlib.metadata.PackageNotFoundError as error:
            raise DuplexError(
                f"controlled OMP requires harbor {PINNED_HARBOR_VERSION}, not installed"
            ) from error
    if version != PINNED_HARBOR_VERSION:
        raise DuplexError(
            f"controlled OMP requires harbor {PINNED_HARBOR_VERSION}, not {version}"
        )
    cls = type(environment)
    if (
        cls.__name__ != "DockerEnvironment"
        or cls.__module__ != "harbor.environments.docker.docker"
    ):
        raise DuplexError("controlled OMP requires Harbor DockerEnvironment")
    if getattr(environment, "_is_windows_container", False):
        raise DuplexError("controlled OMP requires Linux containers")


def driver_install_path(npm_root: Path) -> Path:
    return Path(npm_root) / OMP_PACKAGE / DRIVER_FILENAME


def driver_helpers(package_dir: Path | None = None) -> list[Path]:
    root = package_dir or Path(__file__).resolve().parent
    return sorted(path for path in root.glob("*.ts") if path.is_file())


def driver_launch(script: Path) -> tuple[str, dict[str, str]]:
    return f"bun {script}", {}


# Task metadata, verifier inputs, and reference solutions are private.
SENSITIVE_TASK_FILES = ("task.toml", "tests", "solution")


def _contains(source: Path, forbidden: Path) -> bool:
    """Whether binding `source` exposes `forbidden` wholesale."""
    return source == forbidden or _is_within(forbidden, source)


def _is_within(inner: Path, outer: Path) -> bool:
    try:
        inner.relative_to(outer)
        return True
    except ValueError:
        return False


def _resolved(path: Path) -> Path | None:
    try:
        return path.resolve()
    except OSError:
        return None


def _exposes(source: Path, forbidden: Path, *, sensitive: bool = True) -> bool:
    """Whether binding `source` would expose `forbidden`.

    A `sensitive` root is private in its entirety, so both directions are
    unsafe: binding the directory exposes it wholesale, and binding one
    file inside it exposes that part directly.

    A non-sensitive root is a broad aggregate (the trial directory, the
    task directory) that legitimately contains sanctioned children such
    as the Harbor log mounts and `environment/`. Only the containing
    direction is unsafe there; its private descendants are rejected
    by name instead.
    """
    resolved_source = _resolved(source)
    resolved_forbidden = _resolved(forbidden)
    if resolved_source is None or resolved_forbidden is None:
        return False
    if _contains(resolved_source, resolved_forbidden):
        return True
    if sensitive:
        return _is_within(resolved_source, resolved_forbidden)
    return False


def audit_bind_mounts(
    mounts: list[dict[str, Any]],
    *,
    trial_dir: Path,
    task_dir: Path | None = None,
) -> None:
    trial = Path(trial_dir).resolve()
    # Private in full: binding any part of it leaks controller evidence.
    sensitive = [trial / "yacht-execution"]
    # Aggregates whose sanctioned children (trial/agent, trial/verifier,
    # trial/artifacts, task environment/) must stay mountable.
    aggregates = [trial]
    if task_dir is not None:
        resolved_task = Path(task_dir).resolve()
        aggregates.append(resolved_task)
        sensitive.extend(resolved_task / name for name in SENSITIVE_TASK_FILES)
    for mount in mounts:
        kind = mount.get("type")
        if kind and kind != "bind":
            continue
        source_raw = mount.get("source")
        if not source_raw:
            continue
        source = Path(str(source_raw)).expanduser().resolve()
        for path in sensitive:
            if _exposes(source, path, sensitive=True):
                raise UnsafeMountError(f"bind mount {source} exposes {path}")
        for path in aggregates:
            if _exposes(source, path, sensitive=False):
                raise UnsafeMountError(f"bind mount {source} exposes {path}")


def _compose_document(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        document = yaml.safe_load(text)
    except ImportError:
        document = None
    if not isinstance(document, dict):
        return {}
    return document


def _volume_source(volume: Any, env_dir: Path) -> Path | None:
    if isinstance(volume, str):
        source = volume.split(":", 1)[0]
        if not source or source.startswith("/"):
            return Path(source) if source.startswith("/") else None
        if source.startswith("."):
            return (env_dir / source).resolve()
        candidate = Path(source)
        if candidate.is_absolute():
            return candidate
        return (env_dir / source).resolve()
    if isinstance(volume, dict):
        source = volume.get("source")
        if not source:
            return None
        path = Path(str(source))
        if path.is_absolute():
            return path.resolve()
        return (env_dir / path).resolve()
    return None


def audit_compose_file(
    path: Path, *, trial_dir: Path, task_dir: Path | None = None
) -> None:
    env_dir = path.parent.resolve()
    document = _compose_document(path)
    services = document.get("services") or {}
    mounts: list[dict[str, Any]] = []
    if not isinstance(services, dict):
        services = {}
    for config in services.values():
        if not isinstance(config, dict):
            continue
        for volume in config.get("volumes") or []:
            source = _volume_source(volume, env_dir)
            if source is None:
                continue
            mounts.append({"type": "bind", "source": str(source)})
        build = config.get("build")
        contexts: list[str] = []
        if isinstance(build, str):
            contexts.append(build)
        elif isinstance(build, dict) and build.get("context"):
            contexts.append(str(build["context"]))
        for context in contexts:
            resolved = Path(context)
            resolved = (
                resolved.resolve()
                if resolved.is_absolute()
                else (env_dir / context).resolve()
            )
            try:
                resolved.relative_to(env_dir)
            except ValueError as error:
                raise UnsafeMountError(
                    f"build context {resolved} escapes {env_dir}"
                ) from error
            # `sensitive=False`: a context legitimately sits inside the
            # task directory (environment/), so only a context that
            # *contains* the task source is unsafe here. Containment in
            # the environment dir is already enforced above.
            if task_dir is not None and _exposes(
                resolved, Path(task_dir).resolve(), sensitive=False
            ):
                raise UnsafeMountError(f"build context {resolved} exposes task source")
    audit_bind_mounts(mounts, trial_dir=trial_dir, task_dir=task_dir)


def audit_environment_dir(environment_dir: Path) -> None:
    leaked = environment_dir / "task.toml"
    if leaked.is_file() or leaked.is_symlink():
        raise UnsafeMountError(f"environment dir {environment_dir} contains task.toml")


def compose_exec_argv_from_environment(
    environment: Any, command: str, env: dict[str, str] | None = None
) -> list[str]:
    require_harbor_docker_linux(environment)
    workdir = getattr(environment.task_env_config, "workdir", None)
    user = environment._resolve_user(None)
    merged = environment._merge_env(env)
    return build_compose_exec_argv(
        session_id=environment.session_id,
        environment_dir=environment.environment_dir,
        compose_paths=list(environment._docker_compose_paths),
        command=command,
        workdir=workdir,
        user=user,
        env=merged,
    )


MAX_FRAME_BYTES = 64 * 1024 * 1024
# Grace for the driver process to exit after it acks shutdown. The
# controller allows a longer close budget than the ack budget, so this
# must not pre-empt it and declare a normal exit unconfirmed.
EXIT_GRACE_SECONDS = 15


class LineDriver:
    def __init__(self, process: Any, diagnostics: Path | None = None) -> None:
        self._process = process
        self._diagnostics = diagnostics
        self._stderr_task: Any = None

    def start_diagnostics(self) -> None:
        import asyncio

        stderr = self._process.stderr
        if stderr is None:
            return

        async def drain() -> None:
            written = 0
            while True:
                chunk = await stderr.read(4096)
                if not chunk:
                    return
                if self._diagnostics is None or written >= MAX_FRAME_BYTES:
                    continue
                self._diagnostics.parent.mkdir(parents=True, exist_ok=True)
                with self._diagnostics.open("ab") as handle:
                    handle.write(chunk)
                written += len(chunk)

        self._stderr_task = asyncio.ensure_future(drain())

    async def send(self, payload: dict[str, Any]) -> None:
        import json

        stdin = self._process.stdin
        if stdin is None:
            raise DuplexError("driver stdin is closed")
        stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await stdin.drain()

    async def recv(self) -> dict[str, Any]:
        import asyncio
        import json

        stdout = self._process.stdout
        if stdout is None:
            raise DuplexError("driver stdout is closed")
        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                chunks.append(await stdout.readuntil(b"\n"))
                break
            except asyncio.LimitOverrunError as error:
                # Frame longer than the stream buffer: drain the consumed
                # prefix and keep reading the same line.
                piece = await stdout.readexactly(error.consumed)
                chunks.append(piece)
                total += len(piece)
                if total > MAX_FRAME_BYTES:
                    raise DuplexError("driver frame exceeded limit") from error
            except asyncio.IncompleteReadError as error:
                # EOF. `partial` is empty when the driver exited, so this
                # must terminate instead of looping on a zero-length read.
                if not error.partial:
                    raise DuplexError("driver stdout closed") from error
                chunks.append(error.partial)
                break
        line = b"".join(chunks)
        if not line.strip():
            raise DuplexError("driver stdout closed")
        return json.loads(line.decode("utf-8"))

    async def close(self) -> None:
        import asyncio

        stdin = self._process.stdin
        if stdin is not None:
            stdin.close()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=EXIT_GRACE_SECONDS)
        except (TimeoutError, asyncio.TimeoutError):
            self._process.kill()
            await self._process.wait()
        finally:
            if self._stderr_task is not None:
                self._stderr_task.cancel()


async def audit_launch_privacy(
    environment: Any, *, trial_dir: Path, task_dir: Path | None
) -> None:
    """Reject any launch whose effective mounts expose private state.

    The merged configuration is resolved by Compose itself, using the
    same files, project directory and environment as the launch, so
    JSON overlays, interpolation and relative sources are all covered
    rather than guessed from filenames. Unsupported or unresolvable
    configuration fails closed, before any tokens are spent.
    """
    import asyncio
    import json as _json

    mounts = getattr(environment, "_mounts", None) or []
    audit_bind_mounts(list(mounts), trial_dir=trial_dir, task_dir=task_dir)
    env_dir = getattr(environment, "environment_dir", None)
    if env_dir is not None and Path(env_dir).is_dir():
        audit_environment_dir(Path(env_dir))
    compose_paths = list(getattr(environment, "_docker_compose_paths", []) or [])
    if not compose_paths:
        return
    argv = [
        "docker",
        "compose",
        "--project-name",
        sanitize_compose_project_name(environment.session_id),
        "--project-directory",
        str(Path(environment.environment_dir).resolve()),
    ]
    for path in compose_paths:
        argv.extend(["-f", str(Path(path).resolve())])
    argv.extend(["config", "--format", "json"])
    process = await asyncio.create_subprocess_exec(
        *argv,
        env=environment._compose_env_vars(include_os_env=True),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = (stderr or b"").decode("utf-8", "replace").strip()
        raise UnsafeMountError(
            f"could not resolve compose configuration for audit: {detail}"
        )
    try:
        document = _json.loads(stdout.decode("utf-8", "replace"))
    except ValueError as error:
        raise UnsafeMountError(
            "resolved compose configuration is not valid JSON"
        ) from error
    audit_resolved_compose_document(
        document,
        trial_dir=trial_dir,
        task_dir=task_dir,
        project_directory=Path(environment.environment_dir).resolve(),
    )


def audit_resolved_compose_document(
    document: Any,
    *,
    trial_dir: Path,
    task_dir: Path | None,
    project_directory: Path,
) -> None:
    """Reject private binds in a resolved `docker compose config` document."""
    if not isinstance(document, dict):
        raise UnsafeMountError("resolved compose configuration is not an object")
    services = document.get("services")
    if not isinstance(services, dict):
        raise UnsafeMountError("resolved compose configuration has no services")
    resolved: list[dict[str, Any]] = []
    permitted_context = project_directory.resolve()
    for name, config in services.items():
        if not isinstance(config, dict):
            raise UnsafeMountError(f"unsupported compose service definition: {name!r}")
        build = config.get("build")
        context: str | None = None
        if isinstance(build, str):
            context = build
        elif isinstance(build, dict):
            if build.get("context") is not None:
                context = str(build["context"])
        elif build is not None:
            raise UnsafeMountError(
                f"unsupported compose build definition in service {name!r}"
            )
        if context is not None:
            # A build context is uploaded to the daemon wholesale, so it
            # must stay inside the permitted environment directory even
            # after symlink resolution.
            candidate = Path(context)
            if not candidate.is_absolute():
                candidate = project_directory / candidate
            try:
                candidate = candidate.resolve()
            except OSError as error:
                raise UnsafeMountError(
                    f"unresolvable build context in service {name!r}"
                ) from error
            if candidate != permitted_context:
                try:
                    candidate.relative_to(permitted_context)
                except ValueError as error:
                    raise UnsafeMountError(
                        f"build context {candidate} escapes {permitted_context}"
                    ) from error
        for volume in config.get("volumes") or []:
            if isinstance(volume, dict):
                source = volume.get("source")
                kind = volume.get("type", "bind")
            elif isinstance(volume, str):
                parts = volume.split(":")
                source = parts[0] if len(parts) > 1 else None
                kind = "bind"
            else:
                raise UnsafeMountError(
                    f"unsupported compose volume syntax in service {name!r}"
                )
            if not source or kind != "bind":
                continue
            candidate = Path(str(source))
            if not candidate.is_absolute():
                candidate = project_directory / candidate
            resolved.append({"type": "bind", "source": str(candidate)})
    audit_bind_mounts(resolved, trial_dir=trial_dir, task_dir=task_dir)


def _task_dir_from_trial(trial_dir: Path) -> Path | None:
    import json as _json

    config = trial_dir / "config.json"
    if not config.is_file():
        return None
    try:
        payload = _json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    task = payload.get("task") if isinstance(payload, dict) else None
    path = task.get("path") if isinstance(task, dict) else None
    return Path(str(path)) if path else None


async def start_duplex_driver(
    environment: Any,
    env: dict[str, str] | None = None,
    diagnostics: Path | None = None,
) -> LineDriver:
    import asyncio

    require_harbor_docker_linux(environment)
    trial_paths = getattr(environment, "trial_paths", None)
    trial_dir = getattr(trial_paths, "trial_dir", None)
    if trial_dir is None:
        raise DuplexError("controlled OMP requires a trial directory")
    trial_path = Path(trial_dir)
    await audit_launch_privacy(
        environment,
        trial_dir=trial_path,
        task_dir=_task_dir_from_trial(trial_path),
    )
    if diagnostics is None:
        # Driver stderr is private infrastructure detail: it goes to the
        # trial-private sibling, never the agent-mounted logs.
        diagnostics = trial_path / "yacht-execution" / "driver-stderr.log"
    script = driver_install_path(Path("$root"))
    command = (
        "set -euo pipefail; . ~/.nvm/nvm.sh; "
        f'root="$(npm root -g)"; exec bun "{script.as_posix()}"'
    )
    argv = compose_exec_argv_from_environment(environment, command, env=env)
    process_env = environment._compose_env_vars(include_os_env=True)
    process = await asyncio.create_subprocess_exec(
        *argv,
        env=process_env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=MAX_FRAME_BYTES,
    )
    driver = LineDriver(process, diagnostics)
    driver.start_diagnostics()
    return driver
