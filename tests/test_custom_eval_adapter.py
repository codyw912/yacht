import json
import tempfile
import unittest
from pathlib import Path

from tests.preflight_artifacts import write_preflight_artifact
from yacht.benchmark_grading_collection import collect_benchmark_grading_reports
from yacht.benchmark_launch import write_benchmark_launch_result
from yacht.benchmark_launcher_handoff import write_benchmark_launcher_handoff
from yacht.benchmark_scorecard import write_benchmark_scorecard
from yacht.course_handoff import write_course_handoff
from yacht.custom_eval_harness import main as custom_eval_harness_main
from yacht.custom_eval_predictions_from_attempts import (
    write_custom_eval_predictions_from_attempts,
)
from yacht.preflight_evidence_report import write_preflight_evidence_report
from yacht.real_benchmark_eval import run_real_benchmark_eval
from yacht.regatta import Metrics
from yacht.runtime_instances import write_runtime_instances_plan
from yacht.task_attempts import AgentTaskResult


CONFIG = """
[regatta]
name = "local-custom-eval-smoke"

[preflight]
failure_policy = "abort-group"

[course]
name = "local-custom-eval"
tasks = [
  { id = "custom-1", title = "Complete custom task", difficulty = 1, expect_response = { completed = true, quality = "accepted" }, expect_tool_calls = ["local-smoke"] },
]

[course.adapter]
kind = "custom-eval"
dataset = "local"
split = "smoke"
harness = "local"

[runtimes.local-agent]
backend = "host-nix"
harness = "local-smoke"
flake = "path:."
command = ["local-agent"]

[runtimes.local-agent.preflight]
required = true
checks = [
  { name = "runtime-home-isolated", kind = "path-isolation", env = ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"] },
]

[[vessels]]
name = "local-baseline"
model = "mock"
runtime = "local-agent"

[[vessels]]
name = "local-tool"
model = "mock"
runtime = "local-agent"

[[comparisons]]
name = "local-custom"
course = "local-custom-eval"
vessels = ["local-baseline", "local-tool"]
"""


class CustomEvalAdapterTests(unittest.TestCase):
    def test_custom_eval_predictions_harness_grading_and_scorecard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"
            workspace_path = root / "workspace"
            workspace_path.mkdir()
            _write_completed_attempt(
                logbook_dir=logbook_dir,
                vessel_name="local-baseline",
                response={"completed": True, "quality": "accepted"},
                tool_calls=(),
            )
            _write_completed_attempt(
                logbook_dir=logbook_dir,
                vessel_name="local-tool",
                response={"completed": True, "quality": "accepted"},
                tool_calls=("local-smoke",),
            )
            write_course_handoff(config_path, logbook_dir)
            write_runtime_instances_plan(config_path, logbook_dir, workspace_path)
            _write_preflight(logbook_dir=logbook_dir, vessel_name="local-baseline")
            _write_preflight(logbook_dir=logbook_dir, vessel_name="local-tool")
            write_preflight_evidence_report(logbook_dir)

            baseline_summary = write_custom_eval_predictions_from_attempts(
                config_path=config_path,
                logbook_dir=logbook_dir,
                vessel_name="local-baseline",
                comparison_name="local-custom",
            )
            tool_summary = write_custom_eval_predictions_from_attempts(
                config_path=config_path,
                logbook_dir=logbook_dir,
                vessel_name="local-tool",
                comparison_name="local-custom",
            )
            launcher = write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            self.assertEqual(baseline_summary["adapter"], "custom-eval")
            self.assertEqual(tool_summary["adapter"], "custom-eval")
            baseline_record = _read_jsonl(
                logbook_dir
                / "course-handoff"
                / "custom-eval"
                / "vessels"
                / "local-baseline"
                / "candidate-patches.jsonl"
            )[0]
            self.assertEqual(
                baseline_record["expect_response"],
                {"completed": True, "quality": "accepted"},
            )
            self.assertEqual(baseline_record["expect_tool_calls"], ["local-smoke"])
            self.assertEqual(baseline_record["tool_calls"], [])
            self.assertEqual(launcher["status"], "ready-to-launch")
            command = launcher["comparisons"][0]["vessels"][0]["command"]
            self.assertEqual(command[:4], ["uv", "run", "python", "-m"])
            self.assertEqual(command[4], "yacht.custom_eval_harness")

            launch = write_benchmark_launch_result(logbook_dir=logbook_dir)
            grading = collect_benchmark_grading_reports(
                config_path=config_path,
                logbook_dir=logbook_dir,
            )
            scorecard = write_benchmark_scorecard(logbook_dir)

            self.assertEqual(launch["status"], "complete")
            self.assertEqual(grading["status"], "complete")
            self.assertEqual(scorecard["status"], "complete")
            vessels = scorecard["comparisons"][0]["vessels"]
            self.assertEqual(vessels[0]["resolved_instances"], 0)
            self.assertEqual(vessels[1]["resolved_instances"], 1)
            self.assertEqual(scorecard["comparisons"][0]["delta"]["resolved_instances_delta"], 1)

    def test_real_benchmark_eval_runs_custom_eval_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_config(root)
            logbook_dir = root / "logbook"
            workspace_path = root / "workspace"
            workspace_path.mkdir()

            summary = run_real_benchmark_eval(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
                secret_values={},
                agent_prompt_runner_factory=lambda _instance, _transcript_dir: None,
                task_agent=_CustomTaskAgent(),
                agent_name="local-smoke",
            )

            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["scorecard"]["adapter"]["kind"], "custom-eval")
            self.assertEqual(summary["grading_collection"]["status"], "complete")
            self.assertEqual(summary["benchmark_launch"]["status"], "complete")
            self.assertEqual(
                summary["scorecard"]["comparisons"][0]["delta"][
                    "resolved_instances_delta"
                ],
                0,
            )

    def test_custom_eval_harness_rejects_mixed_vessel_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            records_path = root / "records.jsonl"
            records_path.write_text(
                json.dumps(
                    {
                        "instance_id": "one",
                        "model_name_or_path": "a",
                        "response": {"completed": True},
                        "expect_response": {"completed": True},
                        "tool_calls": [],
                        "expect_tool_calls": [],
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "instance_id": "two",
                        "model_name_or_path": "b",
                        "response": {"completed": True},
                        "expect_response": {"completed": True},
                        "tool_calls": [],
                        "expect_tool_calls": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SystemExit, "exactly one vessel"):
                custom_eval_harness_main(
                    [
                        "--candidate-records",
                        str(records_path),
                        "--report-dir",
                        str(root / "reports"),
                        "--run-id",
                        "run",
                    ]
                )


class _CustomTaskAgent:
    def run_task(
        self,
        *,
        instance,
        task,
        prompt,
        env,
        cwd,
        transcript_path,
    ):
        return AgentTaskResult(
            exit_code=0,
            response=json.dumps(dict(task.expect_response or {"completed": True})),
            tool_calls=(),
            transcript_path=transcript_path,
            metrics=Metrics(tokens=1, duration_seconds=0.1),
        )


def _write_config(root: Path) -> Path:
    config_path = root / "regatta.toml"
    config_path.write_text(CONFIG, encoding="utf-8")
    return config_path


def _write_completed_attempt(
    *,
    logbook_dir: Path,
    vessel_name: str,
    response: dict[str, object],
    tool_calls: tuple[str, ...],
) -> None:
    result = AgentTaskResult(
        exit_code=0,
        response=json.dumps(response),
        tool_calls=tool_calls,
        transcript_path=logbook_dir / "transcripts" / vessel_name / "custom-1.json",
        metrics=Metrics(tokens=1, duration_seconds=0.1),
    )
    _write_task_attempt(logbook_dir=logbook_dir, vessel_name=vessel_name, result=result)


def _write_preflight(*, logbook_dir: Path, vessel_name: str) -> None:
    write_preflight_artifact(
        logbook_dir=logbook_dir,
        comparison_name="local-custom",
        vessel_name=vessel_name,
        status="passed",
        regatta_name="local-custom-eval-smoke",
    )


def _write_task_attempt(*, logbook_dir: Path, vessel_name: str, result) -> None:
    path = logbook_dir / "task-attempts" / "local-custom" / vessel_name / "custom-1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "yacht.task-attempt.v1",
                "regatta": "local-custom-eval-smoke",
                "course": "local-custom-eval",
                "comparison": "local-custom",
                "vessel": vessel_name,
                "model": "mock",
                "rigging": [],
                "runtime": "local-agent",
                "status": "completed",
                "task": {
                    "id": "custom-1",
                    "title": "Complete custom task",
                    "difficulty": 1,
                    "expect_response": {
                        "completed": True,
                        "quality": "accepted",
                    },
                    "expect_tool_calls": ["local-smoke"],
                },
                "runtime_context": {
                    "backend": "host-nix",
                    "harness": "local-smoke",
                    "agent": "local-smoke",
                    "temp_home": "/tmp/home",
                    "workspace_path": "/tmp/workspace",
                    "command_prefix": ["nix", "develop", "path:.", "--command"],
                    "command": ["local-agent"],
                    "cleanup_paths": ["/tmp/home"],
                },
                "prompt": "Complete custom task",
                "agent": {
                    "exit_code": result.exit_code,
                    "response": result.response,
                    "tool_calls": list(result.tool_calls),
                    "transcript_path": str(result.transcript_path),
                },
                "metrics": {
                    "tokens": result.metrics.tokens,
                    "duration_seconds": result.metrics.duration_seconds,
                },
                "secret_refs": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    unittest.main()
