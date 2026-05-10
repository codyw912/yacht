from __future__ import annotations

import json
from pathlib import Path

from yacht.preflight import AgentPromptResult, AgentPromptRunner
from yacht.regatta import RuntimeInstance


class LocalSmokeAgentAdapter:
    def agent_prompt_runner(
        self,
        *,
        instance: RuntimeInstance,
        transcript_dir: Path,
    ) -> AgentPromptRunner:
        def run(prompt: str, env: dict[str, str], cwd: Path) -> AgentPromptResult:
            transcript_path = transcript_dir / "local-smoke-agent.json"
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            response = {"available": True, "configured": True}
            tool_calls = ("local-smoke",)
            transcript_path.write_text(
                json.dumps(
                    {
                        "prompt": prompt,
                        "cwd": str(cwd),
                        "env": _local_smoke_env(env),
                        "response": response,
                        "tool_calls": list(tool_calls),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return AgentPromptResult(
                exit_code=0,
                response=json.dumps(response, sort_keys=True),
                tool_calls=tool_calls,
                transcript_path=transcript_path,
            )

        return run


def _local_smoke_env(env: dict[str, str]) -> dict[str, str]:
    return {
        name: env[name]
        for name in ("LOCAL_TOOL_MODE", "LOCAL_TOOL_STATE")
        if name in env
    }
