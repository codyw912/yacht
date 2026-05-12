from __future__ import annotations

import json
from pathlib import Path

from yacht.preflight import AgentPromptResult, AgentPromptRunner
from yacht.regatta import Metrics, Task, RuntimeInstance
from yacht.task_attempts import AgentTaskResult


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

    def run_task(
        self,
        *,
        task: Task,
        prompt: str,
        env: dict[str, str],
        cwd: Path,
        transcript_path: Path,
    ) -> AgentTaskResult:
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        state_path = env.get("LOCAL_TOOL_STATE")
        tool_calls = ("local-smoke",) if _local_tool_required(env, state_path) else ()
        if state_path is not None and tool_calls:
            _write_local_tool_state(Path(state_path), task)

        response = {
            "completed": True,
            "task_id": task.id,
            "tool_used": bool(tool_calls),
        }
        transcript = {
            "task_id": task.id,
            "prompt": prompt,
            "cwd": str(cwd),
            "env": _local_smoke_env(env),
            "response": response,
            "tool_calls": list(tool_calls),
        }
        if state_path is not None:
            transcript["state_path"] = state_path
        transcript_path.write_text(
            json.dumps(transcript, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        response_text = json.dumps(response, sort_keys=True)
        return AgentTaskResult(
            exit_code=0,
            response=response_text,
            tool_calls=tool_calls,
            transcript_path=transcript_path,
            metrics=Metrics(
                tokens=_estimated_tokens(prompt, response_text),
                duration_seconds=0.0,
            ),
        )


def _local_smoke_env(env: dict[str, str]) -> dict[str, str]:
    return {
        name: env[name]
        for name in ("LOCAL_TOOL_MODE", "LOCAL_TOOL_STATE")
        if name in env
    }


def _local_tool_required(env: dict[str, str], state_path: str | None) -> bool:
    return env.get("LOCAL_TOOL_MODE") == "required" and state_path is not None


def _write_local_tool_state(path: Path, task: Task) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "available": True,
                "configured": True,
                "task_id": task.id,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _estimated_tokens(prompt: str, response: str) -> int:
    return len(prompt.split()) + len(response.split())
