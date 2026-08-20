"""Yacht-owned Harbor agents (ADR 0012).

These classes reuse Harbor's installed-agent implementations for the
harness install and run phases, and additionally apply yacht rigging
steps inside the task container so the tools under test are provisioned
by yacht's own step model.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harbor.agents.installed.base import BaseInstalledAgent, NonZeroAgentExitCodeError
from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.pi import Pi
from harbor.environments.base import BaseEnvironment

from harbor.agents.installed.node_install import nvm_node_install_snippet
from yacht_harbor_agents import declared_support, episodes

from yacht_harbor_agents.rigging import (
    CODEX_PACKAGE,
    PI_NODE_ALIAS_REPAIR_COMMAND,
    PI_PACKAGE,
    codex_run_command,
    omp_install_command,
    omp_run_command,
    rigging_commands,
    version_contains_pin,
)


class RiggingStepError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_episode_plan(
    episodes_kwarg: dict[str, Any] | None, logs_dir: Path
) -> tuple[dict[str, Any] | None, Path | None]:
    """The validated episode plan for this trial, or (None, None).

    Shared by `YachtClaudeCode` and `YachtDeclared`: both key their plan
    off the task identity read from the trial's Harbor config.json,
    which sits one directory up from the agent's own logs_dir.
    """
    if not episodes_kwarg:
        return None, None
    task_name, task_dir = episodes.task_identity(logs_dir.parent)
    plan = episodes.plan_for_task(episodes_kwarg, task_name)
    return plan, task_dir


async def apply_rigging_steps(
    environment: BaseEnvironment,
    steps: list[dict[str, Any]],
) -> None:
    for command in rigging_commands(steps):
        result = await environment.exec(command=command)
        if result.return_code != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RiggingStepError(
                f"rigging step failed with exit code {result.return_code}: "
                f"{command}\n{detail}"
            )


async def capture_resolved_version(
    environment: BaseEnvironment,
    logs_dir: Path,
    command: str,
    expected: str | None,
) -> str:
    result = await environment.exec(command=command)
    version = (result.stdout or "").strip()
    if result.return_code != 0 or not version:
        detail = (result.stderr or result.stdout or "").strip()
        raise RiggingStepError(
            f"failed to capture resolved version ({command}): {detail}"
        )
    if expected and not version_contains_pin(version, expected):
        raise RiggingStepError(
            f"resolved version {version} does not match configured pin {expected}"
        )
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "resolved-version.txt").write_text(version + "\n", encoding="utf-8")
    return version


async def run_episode_verifier(
    environment: BaseEnvironment,
    task_dir: Path,
    episode_dir: Path,
    verifier_dir: Path,
) -> float | None:
    """Mirror harbor's verifier protocol between episodes (ADR 0025).

    The task's verify_between flag asserts the verifier is
    side-effect-free; upload, exec, and removal are hygiene, not a
    guarantee. The reward returned here never grades the trial — the
    final harbor-run verifier remains grading truth.
    """
    tests_dir = task_dir / "tests"
    if not tests_dir.is_dir():
        raise episodes.EpisodePlanError(
            f"verify_between requires a tests directory at {tests_dir}"
        )
    await environment.upload_dir(source_dir=tests_dir, target_dir="/tests")
    await environment.exec(command="chmod +x /tests/test.sh", user="root")
    await environment.exec(
        command="/tests/test.sh > /logs/verifier/episode-stdout.txt 2>&1 || true"
    )
    if not environment.capabilities.mounted:
        await environment.download_dir(
            source_dir="/logs/verifier", target_dir=str(verifier_dir)
        )
    reward = episodes.read_reward(verifier_dir)
    episode_dir.mkdir(parents=True, exist_ok=True)
    for name in ("reward.json", "reward.txt", "episode-stdout.txt"):
        source = verifier_dir / name
        if source.is_file():
            source.rename(episode_dir / name)
    await environment.exec(
        command=(
            "rm -rf /tests /logs/verifier/reward.json "
            "/logs/verifier/reward.txt /logs/verifier/episode-stdout.txt"
        ),
        user="root",
    )
    return reward


class YachtClaudeCode(ClaudeCode):
    @staticmethod
    def name() -> str:
        return "yacht-claude-code"

    def __init__(
        self,
        logs_dir: Path,
        rigging_steps: list[dict[str, Any]] | None = None,
        episodes: dict[str, Any] | None = None,
        *args,
        **kwargs,
    ):
        self._rigging_steps = list(rigging_steps or [])
        self._episodes_kwarg = dict(episodes or {})
        self._episode_costs: list[float | None] = []
        super().__init__(logs_dir, *args, **kwargs)

    async def install(self, environment: BaseEnvironment) -> None:
        await super().install(environment)
        await apply_rigging_steps(environment, self._rigging_steps)

    async def run(self, instruction, environment: BaseEnvironment, context) -> None:
        plan, task_dir = self._episode_plan()
        if plan is None:
            await super().run(instruction, environment, context)
            return
        await self._run_episodes(plan, task_dir, instruction, environment, context)

    def _episode_plan(self) -> tuple[dict[str, Any] | None, Path | None]:
        return resolve_episode_plan(self._episodes_kwarg, self.logs_dir)

    async def _run_episodes(
        self,
        plan: dict[str, Any],
        task_dir: Path,
        instruction: str,
        environment: BaseEnvironment,
        context,
    ) -> None:
        episodes_dir = self.logs_dir / "episodes"
        if plan.get("max_turns") is not None:
            # Touches harbor internals directly: CliFlag resolution lives
            # in agents/installed/base.py (verified fact carried from
            # Tasks 3-4). Re-check this on every harbor image upgrade.
            self._flag_kwargs["max_turns"] = plan["max_turns"]
            self._resolved_flags = self._resolve_flag_values()
        records: list[dict[str, Any]] = []
        to_resolution: int | None = None
        failure: Exception | None = None
        try:
            for index in range(1, plan["max"] + 1):
                text = instruction if index == 1 else plan["instructions"][index - 2]
                episode_dir = episodes_dir / f"{index:03d}"
                episode_dir.mkdir(parents=True, exist_ok=True)
                (episode_dir / "instruction.md").write_text(text, encoding="utf-8")
                started_at = _utc_now()
                timed_out = False
                error: Exception | None = None
                try:
                    timeout = plan.get("timeout_seconds")
                    if timeout:
                        async with asyncio.timeout(timeout):
                            await super().run(text, environment, context)
                    else:
                        await super().run(text, environment, context)
                except TimeoutError:
                    timed_out = True
                    await environment.exec(
                        command="pkill -f 'claude --verbose' || true"
                    )
                except NonZeroAgentExitCodeError as exc:
                    error = exc
                finished_at = _utc_now()
                result = self._snapshot_episode(episode_dir)
                ended = episodes.claude_episode_ended(
                    result["subtype"], timed_out, error is not None
                )
                self._episode_costs.append(result["cost_usd"])
                record = episodes.episode_record(
                    index=index,
                    ended=ended,
                    started_at=started_at,
                    finished_at=finished_at,
                    usage=result["usage"],
                    cost_usd=result["cost_usd"],
                )
                if ended == episodes.ENDED_ERROR:
                    records.append(record)
                    failure = error or RuntimeError(
                        f"episode {index} ended in error without an exception"
                    )
                    break
                # Appended before verify_between runs (not after) so a
                # completed episode is never dropped from summary.json if
                # the inter-episode verifier itself raises (upload/exec/
                # download/rename failure) — the reward assignment below
                # mutates this same dict by reference once it lands.
                records.append(record)
                if (
                    plan["verify_between"]
                    and index < plan["max"]
                    and to_resolution is None
                ):
                    reward = await run_episode_verifier(
                        environment,
                        task_dir,
                        episode_dir,
                        self.logs_dir.parent / "verifier",
                    )
                    if reward is not None:
                        record["reward"] = reward
                        if reward >= 1.0:
                            to_resolution = index
                if to_resolution is not None:
                    break
        finally:
            if records:
                episodes.write_relay_summary(episodes_dir, records, to_resolution)
        if failure is not None:
            raise failure

    def _snapshot_episode(self, episode_dir: Path) -> dict[str, Any]:
        stream_path = self.logs_dir / "claude-code.txt"
        text = ""
        if stream_path.is_file():
            text = stream_path.read_text(encoding="utf-8", errors="replace")
            (episode_dir / "claude-code.txt").write_text(text, encoding="utf-8")
        manifest = episodes.sessions_manifest(self.logs_dir / "sessions" / "projects")
        (episode_dir / "sessions-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return episodes.parse_claude_stream_result(text)

    def populate_context_post_run(self, context) -> None:
        super().populate_context_post_run(context)
        if self._episode_costs and all(
            cost is not None for cost in self._episode_costs
        ):
            context.cost_usd = sum(self._episode_costs)


class YachtPi(Pi):
    @staticmethod
    def name() -> str:
        return "yacht-pi"

    def __init__(
        self,
        logs_dir: Path,
        rigging_steps: list[dict[str, Any]] | None = None,
        *args,
        **kwargs,
    ):
        self._rigging_steps = list(rigging_steps or [])
        super().__init__(logs_dir, *args, **kwargs)

    async def install(self, environment: BaseEnvironment) -> None:
        # Replaces (not extends) harbor's Pi install: same shape, but
        # the current pi npm package (PI_PACKAGE) instead of the retired
        # @mariozechner scope harbor 0.20.0 still names. Drop this
        # override when harbor's Pi agent installs the new scope.
        version_spec = f"@{self._version}" if self._version else "@latest"
        await self.exec_as_root(
            environment,
            command="apt-get update && apt-get install -y curl",
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"{nvm_node_install_snippet()} && "
                f"npm install -g {PI_PACKAGE}{version_spec} && "
                "pi --version"
            ),
        )
        result = await environment.exec(command=PI_NODE_ALIAS_REPAIR_COMMAND)
        if result.return_code != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RiggingStepError(
                "node alias repair failed with exit code "
                f"{result.return_code}: {PI_NODE_ALIAS_REPAIR_COMMAND}\n{detail}"
            )
        await apply_rigging_steps(environment, self._rigging_steps)


def _read_local_stream(logs_dir: Path, name: str, parse_result) -> dict[str, Any]:
    path = logs_dir / name
    if not path.is_file():
        return {"ended": None, "usage": None, "cost_usd": None}
    return parse_result(path.read_text(encoding="utf-8", errors="replace"))


async def run_jsonl_episodes(
    *,
    logs_dir: Path,
    plan: dict[str, Any],
    task_dir: Path,
    instruction: str,
    environment: BaseEnvironment,
    command_for,
    stream_name: str,
    pkill_pattern: str,
    parse_result,
) -> tuple[list[dict[str, Any] | None], list[float | None]]:
    """Cold-session relay for a JSONL-emitting CLI (OMP, Codex).

    Each episode starts a fresh process. `--no-session` / `--ephemeral`
    stay on the command; files are the only continuity channel. A
    timeout is a normal episode ending. A nonzero exit aborts the trial
    after the episodes recorded so far are written.
    """
    episodes_dir = logs_dir / "episodes"
    records: list[dict[str, Any]] = []
    usages: list[dict[str, Any] | None] = []
    costs: list[float | None] = []
    to_resolution: int | None = None
    failure: Exception | None = None
    try:
        for index in range(1, plan["max"] + 1):
            text = instruction if index == 1 else plan["instructions"][index - 2]
            episode_dir = episodes_dir / f"{index:03d}"
            episode_dir.mkdir(parents=True, exist_ok=True)
            (episode_dir / "instruction.md").write_text(text, encoding="utf-8")
            started_at = _utc_now()
            timed_out = False
            error: Exception | None = None
            try:
                timeout = plan.get("timeout_seconds")
                if timeout:
                    async with asyncio.timeout(timeout):
                        result = await environment.exec(command=command_for(text))
                else:
                    result = await environment.exec(command=command_for(text))
                if result.return_code != 0:
                    error = NonZeroAgentExitCodeError(
                        f"{stream_name} exited with code {result.return_code} "
                        f"in episode {index}"
                    )
            except TimeoutError:
                timed_out = True
                cleanup_command, cleanup_env = episodes.process_cleanup_request(
                    pkill_pattern
                )
                cleanup = await environment.exec(
                    command=cleanup_command,
                    env=cleanup_env,
                )
                if cleanup.return_code != 0:
                    detail = (cleanup.stderr or cleanup.stdout or "").strip()
                    raise RuntimeError(
                        f"failed to terminate timed-out {stream_name} process: "
                        f"{detail or pkill_pattern}"
                    )
            finished_at = _utc_now()
            stream = episodes.snapshot_stream(logs_dir, episode_dir, stream_name)
            parsed = parse_result(stream)
            ended = episodes.jsonl_episode_ended(
                parsed.get("ended"), timed_out, error is not None
            )
            usages.append(parsed.get("usage"))
            costs.append(parsed.get("cost_usd"))
            record = episodes.episode_record(
                index=index,
                ended=ended,
                started_at=started_at,
                finished_at=finished_at,
                usage=parsed.get("usage"),
                cost_usd=parsed.get("cost_usd"),
            )
            if ended == episodes.ENDED_ERROR:
                records.append(record)
                failure = error or RuntimeError(
                    f"episode {index} ended in error without an exception"
                )
                break
            records.append(record)
            if plan["verify_between"] and index < plan["max"] and to_resolution is None:
                reward = await run_episode_verifier(
                    environment,
                    task_dir,
                    episode_dir,
                    logs_dir.parent / "verifier",
                )
                if reward is not None:
                    record["reward"] = reward
                    if reward >= 1.0:
                        to_resolution = index
            if to_resolution is not None:
                break
    finally:
        if records:
            episodes.write_relay_summary(episodes_dir, records, to_resolution)
    if failure is not None:
        raise failure
    return usages, costs


class YachtOmp(BaseInstalledAgent):
    """Isolated OMP install plus yacht rigging (no user-home copy)."""

    @staticmethod
    def name() -> str:
        return "yacht-omp"

    def __init__(
        self,
        logs_dir: Path,
        rigging_steps: list[dict[str, Any]] | None = None,
        episodes: dict[str, Any] | None = None,
        *args,
        **kwargs,
    ):
        self._rigging_steps = list(rigging_steps or [])
        self._episodes_kwarg = dict(episodes or {})
        self._recorded_usage: dict[str, int] | None = None
        self._recorded_cost: float | None = None
        super().__init__(logs_dir, *args, **kwargs)

    def get_version_command(self) -> str | None:
        return "omp --version"

    async def install(self, environment: BaseEnvironment) -> None:
        version_spec = f"@{self._version}" if self._version else "@latest"
        await self.exec_as_root(
            environment,
            command="apt-get update && apt-get install -y curl",
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"{nvm_node_install_snippet()} && "
                f"{omp_install_command(version_spec)}"
            ),
        )
        result = await environment.exec(command=PI_NODE_ALIAS_REPAIR_COMMAND)
        if result.return_code != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RiggingStepError(
                "node alias repair failed with exit code "
                f"{result.return_code}: {PI_NODE_ALIAS_REPAIR_COMMAND}\n{detail}"
            )
        await apply_rigging_steps(environment, self._rigging_steps)
        resolved = await capture_resolved_version(
            environment,
            self.logs_dir,
            ". ~/.nvm/nvm.sh; omp --version",
            self._version,
        )
        self._version = resolved

    async def run(self, instruction, environment: BaseEnvironment, context) -> None:
        plan, task_dir = resolve_episode_plan(self._episodes_kwarg, self.logs_dir)
        if plan is not None:
            usages, costs = await run_jsonl_episodes(
                logs_dir=self.logs_dir,
                plan=plan,
                task_dir=task_dir,
                instruction=str(instruction),
                environment=environment,
                command_for=lambda text: omp_run_command(
                    instruction=text,
                    model=str(self.model_name or "") or None,
                ),
                stream_name="omp.jsonl",
                pkill_pattern="omp -p --mode json",
                parse_result=episodes.parse_omp_stream_result,
            )
            self._recorded_usage = episodes.merge_stream_usages(usages)
            self._recorded_cost = episodes.merge_stream_costs(costs)
            return
        result = await environment.exec(
            command=omp_run_command(
                instruction=str(instruction),
                model=str(self.model_name or "") or None,
            )
        )
        if result.return_code != 0:
            raise NonZeroAgentExitCodeError(
                f"omp exited with code {result.return_code}"
            )
        parsed = _read_local_stream(
            self.logs_dir, "omp.jsonl", episodes.parse_omp_stream_result
        )
        self._recorded_usage = parsed.get("usage")
        self._recorded_cost = parsed.get("cost_usd")

    def populate_context_post_run(self, context) -> None:
        super().populate_context_post_run(context)
        episodes.apply_usage_to_context(
            context,
            self._recorded_usage,
            self._recorded_cost,
            input_includes_cache=False,
        )


class YachtCodex(BaseInstalledAgent):
    """Isolated Codex install plus yacht rigging (no user-home copy)."""

    @staticmethod
    def name() -> str:
        return "yacht-codex"

    def __init__(
        self,
        logs_dir: Path,
        rigging_steps: list[dict[str, Any]] | None = None,
        episodes: dict[str, Any] | None = None,
        *args,
        **kwargs,
    ):
        self._rigging_steps = list(rigging_steps or [])
        self._episodes_kwarg = dict(episodes or {})
        self._recorded_usage: dict[str, int] | None = None
        self._recorded_cost: float | None = None
        super().__init__(logs_dir, *args, **kwargs)

    def get_version_command(self) -> str | None:
        return "codex --version"

    async def install(self, environment: BaseEnvironment) -> None:
        version_spec = f"@{self._version}" if self._version else "@latest"
        await self.exec_as_root(
            environment,
            command="apt-get update && apt-get install -y curl",
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"{nvm_node_install_snippet()} && "
                f"npm install -g {CODEX_PACKAGE}{version_spec} && "
                "codex --version"
            ),
        )
        result = await environment.exec(command=PI_NODE_ALIAS_REPAIR_COMMAND)
        if result.return_code != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RiggingStepError(
                "node alias repair failed with exit code "
                f"{result.return_code}: {PI_NODE_ALIAS_REPAIR_COMMAND}\n{detail}"
            )
        await apply_rigging_steps(environment, self._rigging_steps)
        resolved = await capture_resolved_version(
            environment,
            self.logs_dir,
            ". ~/.nvm/nvm.sh; codex --version",
            self._version,
        )
        self._version = resolved

    async def run(self, instruction, environment: BaseEnvironment, context) -> None:
        plan, task_dir = resolve_episode_plan(self._episodes_kwarg, self.logs_dir)
        if plan is not None:
            usages, costs = await run_jsonl_episodes(
                logs_dir=self.logs_dir,
                plan=plan,
                task_dir=task_dir,
                instruction=str(instruction),
                environment=environment,
                command_for=lambda text: codex_run_command(
                    instruction=text,
                    model=str(self.model_name or "") or None,
                ),
                stream_name="codex.jsonl",
                pkill_pattern="codex exec --json",
                parse_result=episodes.parse_codex_stream_result,
            )
            self._recorded_usage = episodes.merge_stream_usages(usages)
            self._recorded_cost = episodes.merge_stream_costs(costs)
            return
        result = await environment.exec(
            command=codex_run_command(
                instruction=str(instruction),
                model=str(self.model_name or "") or None,
            )
        )
        if result.return_code != 0:
            raise NonZeroAgentExitCodeError(
                f"codex exited with code {result.return_code}"
            )
        parsed = _read_local_stream(
            self.logs_dir, "codex.jsonl", episodes.parse_codex_stream_result
        )
        self._recorded_usage = parsed.get("usage")
        self._recorded_cost = parsed.get("cost_usd")

    def populate_context_post_run(self, context) -> None:
        super().populate_context_post_run(context)
        episodes.apply_usage_to_context(
            context,
            self._recorded_usage,
            self._recorded_cost,
            input_includes_cache=True,
        )


class YachtDeclared(BaseInstalledAgent):
    """Generic Harbor agent for config-declared harnesses (ADR 0016).

    The declaration arrives via agent kwargs. The artifact is resolved
    and checksum-verified on the launcher side, uploaded into the task
    container, and verified again in-container before the harness runs.
    Evidence follows the yacht.harness-evidence.v1 contract and maps
    into the trial result; a run without valid evidence is a trial
    error, never an estimated measurement.
    """

    @staticmethod
    def name() -> str:
        return "yacht-declared"

    def __init__(
        self,
        logs_dir: Path,
        declaration: dict[str, Any],
        rigging_steps: list[dict[str, Any]] | None = None,
        episodes: dict[str, Any] | None = None,
        *args,
        **kwargs,
    ):
        self._declaration = dict(declaration)
        self._rigging_steps = list(rigging_steps or [])
        self._episodes_kwarg = dict(episodes or {})
        self._evidence: dict[str, Any] | None = None
        super().__init__(logs_dir, *args, **kwargs)

    def get_version_command(self) -> str | None:
        return f"{declared_support.binary_path(self._declaration)} --version"

    async def install(self, environment: BaseEnvironment) -> None:
        artifact = self._resolve_artifact()
        declared_support.verify_artifact(
            artifact, str(self._declaration["install"]["sha256"])
        )
        binary = declared_support.binary_path(self._declaration)
        await environment.exec(
            command=f"mkdir -p {declared_support.CONTAINER_BINARY_DIR}",
            user="root",
        )
        await environment.upload_file(artifact, binary)
        for command in declared_support.install_commands(self._declaration):
            result = await environment.exec(command=command, user="root")
            if result.return_code != 0:
                detail = (result.stderr or result.stdout or "").strip()
                raise RuntimeError(
                    f"declared harness install command failed "
                    f"({result.return_code}): {command}\n{detail}"
                )
        await apply_rigging_steps(environment, self._rigging_steps)

    def _resolve_artifact(self) -> Path:
        install = self._declaration.get("install") or {}
        path = install.get("path")
        if path:
            return Path(str(path))
        url = install.get("url")
        if not url:
            raise RuntimeError("declared harness install must set url or path")
        target = self.logs_dir / "harness-artifact"
        target.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(str(url), target)
        return target

    async def run(self, instruction, environment: BaseEnvironment, context) -> None:
        plan, task_dir = resolve_episode_plan(self._episodes_kwarg, self.logs_dir)
        if plan is not None:
            await self._run_episodes(plan, task_dir, instruction, environment, context)
            return
        command = declared_support.run_command(
            self._declaration,
            model=str(self.model_name or ""),
            instruction=instruction,
        )
        result = await environment.exec(command=command)
        (self.logs_dir / "run-stdout.txt").write_text(
            result.stdout or "", encoding="utf-8"
        )
        (self.logs_dir / "run-stderr.txt").write_text(
            result.stderr or "", encoding="utf-8"
        )
        if result.return_code != 0:
            raise RuntimeError(
                f"declared harness exited with code {result.return_code}"
            )
        self._evidence = await self._collect_evidence(
            environment, result, self.logs_dir
        )

    async def _run_episodes(
        self,
        plan: dict[str, Any],
        task_dir: Path,
        instruction: str,
        environment: BaseEnvironment,
        context,
    ) -> None:
        episodes_dir = self.logs_dir / "episodes"
        records: list[dict[str, Any]] = []
        per_episode_evidence: list[dict[str, Any]] = []
        to_resolution: int | None = None
        failure: Exception | None = None
        try:
            for index in range(1, plan["max"] + 1):
                text = instruction if index == 1 else plan["instructions"][index - 2]
                episode_dir = episodes_dir / f"{index:03d}"
                episode_dir.mkdir(parents=True, exist_ok=True)
                (episode_dir / "instruction.md").write_text(text, encoding="utf-8")
                command = declared_support.run_command(
                    self._declaration,
                    model=str(self.model_name or ""),
                    instruction=text,
                    max_turns=plan.get("max_turns"),
                )
                started_at = _utc_now()
                timed_out = False
                result = None
                try:
                    timeout = plan.get("timeout_seconds")
                    if timeout:
                        async with asyncio.timeout(timeout):
                            result = await environment.exec(command=command)
                    else:
                        result = await environment.exec(command=command)
                except TimeoutError:
                    timed_out = True
                    binary = declared_support.binary_path(self._declaration)
                    await environment.exec(command=f"pkill -f {binary} || true")
                    # No evidence was collected this episode, but the
                    # harness may have partially written the container
                    # evidence file before being killed; clear it so the
                    # next episode cannot inherit stale evidence.
                    await environment.exec(
                        command=f"rm -f {declared_support.CONTAINER_EVIDENCE_PATH}"
                    )
                finished_at = _utc_now()

                # Mirrors YachtClaudeCode._run_episodes: a timeout is a
                # normal (if unproductive) episode ending, not a trial
                # failure — the relay tries the next episode. Only a
                # nonzero exit or invalid evidence aborts the trial.
                if timed_out:
                    record = episodes.episode_record(
                        index=index,
                        ended=episodes.ENDED_TIMEOUT,
                        started_at=started_at,
                        finished_at=finished_at,
                    )
                elif result.return_code != 0:
                    (episode_dir / "run-stdout.txt").write_text(
                        result.stdout or "", encoding="utf-8"
                    )
                    (episode_dir / "run-stderr.txt").write_text(
                        result.stderr or "", encoding="utf-8"
                    )
                    records.append(
                        episodes.episode_record(
                            index=index,
                            ended=episodes.ENDED_ERROR,
                            started_at=started_at,
                            finished_at=finished_at,
                        )
                    )
                    failure = RuntimeError(
                        f"declared harness exited with code {result.return_code} "
                        f"in episode {index}"
                    )
                    break
                else:
                    (episode_dir / "run-stdout.txt").write_text(
                        result.stdout or "", encoding="utf-8"
                    )
                    (episode_dir / "run-stderr.txt").write_text(
                        result.stderr or "", encoding="utf-8"
                    )
                    try:
                        evidence = await self._collect_evidence(
                            environment, result, episode_dir
                        )
                    except Exception as exc:
                        # An episode that ran but yielded invalid/unreadable
                        # evidence is a trial error, same as a nonzero exit.
                        records.append(
                            episodes.episode_record(
                                index=index,
                                ended=episodes.ENDED_ERROR,
                                started_at=started_at,
                                finished_at=finished_at,
                            )
                        )
                        failure = exc
                        break

                    await environment.exec(
                        command=f"rm -f {declared_support.CONTAINER_EVIDENCE_PATH}"
                    )
                    per_episode_evidence.append(evidence)
                    usage_source = evidence.get("usage", {})
                    usage = {
                        key: usage_source[key]
                        for key in (
                            "input_tokens",
                            "output_tokens",
                            "cache_read_tokens",
                        )
                        if key in usage_source
                    }
                    cost_usd = declared_support.context_fields(evidence)["cost_usd"]
                    record = episodes.episode_record(
                        index=index,
                        ended=episodes.ENDED_NATURAL,
                        started_at=started_at,
                        finished_at=finished_at,
                        usage=usage,
                        cost_usd=cost_usd,
                    )

                # Appended before verify_between runs (not after) so a
                # completed episode is never dropped from summary.json if
                # the inter-episode verifier itself raises (upload/exec/
                # download/rename failure) — the reward assignment below
                # mutates this same dict by reference once it lands.
                records.append(record)
                if (
                    plan["verify_between"]
                    and index < plan["max"]
                    and to_resolution is None
                ):
                    reward = await run_episode_verifier(
                        environment,
                        task_dir,
                        episode_dir,
                        self.logs_dir.parent / "verifier",
                    )
                    if reward is not None:
                        record["reward"] = reward
                        if reward >= 1.0:
                            to_resolution = index
                if to_resolution is not None:
                    break
        finally:
            if records:
                episodes.write_relay_summary(episodes_dir, records, to_resolution)
        if failure is not None:
            raise failure
        if not per_episode_evidence:
            # Reachable not just when every episode times out, but also
            # when a timed-out episode's inter-episode verifier reports
            # resolution (to_resolution set) before any episode ever
            # completed a measured run. Resolution does not exempt the
            # relay from the evidence requirement below.
            raise RuntimeError(
                "declared episodic relay produced no harness evidence (no "
                "episode completed a measured run); a run without valid "
                "evidence is a trial error even when an inter-episode "
                "verifier reported resolution"
            )
        merged = episodes.merged_declared_evidence(per_episode_evidence)
        validated = declared_support.validate_evidence(merged)
        (self.logs_dir / "harness-evidence.json").write_text(
            json.dumps(validated, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self._evidence = validated

    async def _collect_evidence(
        self,
        environment: BaseEnvironment,
        result: Any,
        target: Path,
    ) -> dict[str, Any]:
        if self._declaration.get("evidence", "stdout") == "file":
            local = target / "harness-evidence.json"
            await environment.download_file(
                declared_support.CONTAINER_EVIDENCE_PATH, local
            )
            payload = json.loads(local.read_text(encoding="utf-8"))
        else:
            lines = [
                line for line in (result.stdout or "").splitlines() if line.strip()
            ]
            if not lines:
                raise RuntimeError(
                    "declared harness exited 0 without emitting evidence"
                )
            payload = json.loads(lines[-1])
            (target / "harness-evidence.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return declared_support.normalize_evidence(self._declaration, payload)

    def populate_context_post_run(self, context) -> None:
        if self._evidence is None:
            return
        fields = declared_support.context_fields(self._evidence)
        context.n_input_tokens = fields["n_input_tokens"]
        context.n_output_tokens = fields["n_output_tokens"]
        context.n_cache_tokens = fields["n_cache_tokens"]
        if fields["cost_usd"] is not None:
            context.cost_usd = fields["cost_usd"]
