"""Yacht-owned Harbor agents (ADR 0012).

These classes reuse Harbor's installed-agent implementations for the
harness install and run phases, and additionally apply yacht rigging
steps inside the task container so the tools under test are provisioned
by yacht's own step model.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from harbor.agents.installed.base import BaseInstalledAgent
from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.pi import Pi
from harbor.environments.base import BaseEnvironment

from harbor.agents.installed.node_install import nvm_node_install_snippet

from yacht_harbor_agents import declared_support
from yacht_harbor_agents.rigging import (
    PI_NODE_ALIAS_REPAIR_COMMAND,
    PI_PACKAGE,
    rigging_commands,
)


class RiggingStepError(RuntimeError):
    pass


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


class YachtClaudeCode(ClaudeCode):
    @staticmethod
    def name() -> str:
        return "yacht-claude-code"

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
        await super().install(environment)
        await apply_rigging_steps(environment, self._rigging_steps)


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
        *args,
        **kwargs,
    ):
        self._declaration = dict(declaration)
        self._rigging_steps = list(rigging_steps or [])
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
            raise RuntimeError(
                "declared harness install must set url or path"
            )
        target = self.logs_dir / "harness-artifact"
        target.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(str(url), target)
        return target

    async def run(self, instruction, environment: BaseEnvironment, context) -> None:
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
        self._evidence = await self._collect_evidence(environment, result)

    async def _collect_evidence(
        self,
        environment: BaseEnvironment,
        result: Any,
    ) -> dict[str, Any]:
        if self._declaration.get("evidence", "stdout") == "file":
            local = self.logs_dir / "harness-evidence.json"
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
            (self.logs_dir / "harness-evidence.json").write_text(
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
