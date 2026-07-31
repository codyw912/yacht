import json
import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import (
    Comparison,
    Course,
    Metrics,
    Regatta,
    RiggingRecipe,
    RuntimeInstance,
    RuntimeRecipe,
    RuntimeSetupResult,
    SecretReference,
    Task,
    Vessel,
)
from yacht.reports.task_attempt_scorecard import write_task_attempt_scorecard
from yacht.workflows.task_attempts import AgentTaskResult, write_task_attempt


class TaskAttemptTests(unittest.TestCase):
    def test_write_task_attempt_records_agent_output_and_runtime_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_path = (
                root / "logbook/task-attempts/pi-vs-pi-fff/pi-plus-fff/task-1.json"
            )
            transcript_path = (
                root / "logbook/transcripts/pi-vs-pi-fff/pi-plus-fff/task-1.json"
            )
            instance = RuntimeInstance(
                runtime=RuntimeRecipe(
                    name="pi-runtime",
                    backend="host-nix",
                    flake="github:example/pi",
                    command=("pi",),
                    env={"ANTHROPIC_API_KEY": "{secret:anthropic}"},
                    required_secrets=("anthropic",),
                ),
                temp_home=root / "runtime/pi-plus-fff/home",
                workspace_path=root / "workspace",
                env={
                    "HOME": str(root / "runtime/pi-plus-fff/home"),
                    "ANTHROPIC_API_KEY": "secret-value",
                },
                command_prefix=("nix", "develop", "github:example/pi", "--command"),
                cleanup_paths=(root / "runtime/pi-plus-fff",),
                setup_results=(
                    RuntimeSetupResult(
                        origin="rigging",
                        origin_name="pi-fff",
                        action="config-file",
                        target=".config/tool/settings.json",
                        argv=(),
                        exit_code=0,
                        stdout="wrote settings",
                        stderr="",
                    ),
                ),
            )
            regatta = Regatta(
                name="pi-fff-comparison",
                course=Course(
                    name="tiny-smoke-course",
                    tasks=(
                        Task(
                            id="task-1",
                            title="Touch a marker file",
                            difficulty=1,
                        ),
                    ),
                ),
                vessels=(
                    Vessel(
                        name="pi-plus-fff",
                        model="pi",
                        rigging=("fff",),
                        runtime="pi-runtime",
                    ),
                ),
                secrets={
                    "anthropic": SecretReference(
                        source="env",
                        name="ANTHROPIC_API_KEY",
                    ),
                    "fff-license": SecretReference(
                        source="file",
                        path="/run/secrets/fff-license",
                    ),
                },
                rigging_recipes={
                    "fff": RiggingRecipe(
                        name="fff",
                        required_secrets=("fff-license",),
                    )
                },
            )

            artifact = write_task_attempt(
                artifact_path=artifact_path,
                regatta=regatta,
                comparison=Comparison(
                    name="pi-vs-pi-fff",
                    course="tiny-smoke-course",
                    vessels=("pi-plus-fff",),
                ),
                vessel=regatta.vessels[0],
                task=regatta.course.tasks[0],
                instance=instance,
                prompt="Create the requested marker file.",
                result=AgentTaskResult(
                    exit_code=0,
                    response="done",
                    tool_calls=("fff",),
                    transcript_path=transcript_path,
                    metrics=Metrics(tokens=1234, duration_seconds=12.5),
                    machine_evidence={
                        "format": "pi-jsonl",
                        "provider": "anthropic",
                        "model": "claude-haiku-4-5",
                        "usage": {
                            "input": 1000,
                            "output": 234,
                            "totalTokens": 1234,
                        },
                        "cost": {"total": 0.00123},
                    },
                ),
            )

            self.assertTrue(artifact_path.is_file())
            self.assertEqual(
                json.loads(artifact_path.read_text(encoding="utf-8")),
                artifact,
            )
            self.assertEqual(artifact["schema"], "yacht.task-attempt.v1")
            self.assertEqual(artifact["status"], "completed")
            self.assertEqual(artifact["comparison"], "pi-vs-pi-fff")
            self.assertEqual(artifact["vessel"], "pi-plus-fff")
            self.assertEqual(artifact["task"]["id"], "task-1")
            self.assertEqual(artifact["agent"]["exit_code"], 0)
            self.assertEqual(artifact["agent"]["tool_calls"], ["fff"])
            self.assertEqual(artifact["agent"]["transcript_path"], str(transcript_path))
            self.assertEqual(
                artifact["runtime_context"]["setup_results"],
                [
                    {
                        "origin": "rigging",
                        "origin_name": "pi-fff",
                        "action": "config-file",
                        "target": ".config/tool/settings.json",
                        "argv": [],
                        "exit_code": 0,
                    }
                ],
            )
            self.assertEqual(
                artifact["agent"]["machine_evidence"],
                {
                    "format": "pi-jsonl",
                    "provider": "anthropic",
                    "model": "claude-haiku-4-5",
                    "usage": {
                        "input": 1000,
                        "output": 234,
                        "totalTokens": 1234,
                    },
                    "cost": {"total": 0.00123},
                },
            )
            self.assertEqual(artifact["metrics"]["tokens"], 1234)
            self.assertEqual(
                artifact["secret_refs"],
                [
                    {
                        "name": "anthropic",
                        "source": "env",
                        "ref": "ANTHROPIC_API_KEY",
                        "redacted": True,
                    },
                    {
                        "name": "fff-license",
                        "source": "file",
                        "ref": "/run/secrets/fff-license",
                        "redacted": True,
                    },
                ],
            )
            self.assertNotIn("secret-value", json.dumps(artifact))

            scorecard = write_task_attempt_scorecard(root / "logbook")
            vessel_score = scorecard["comparisons"][0]["vessels"][0]
            comparison_summary = scorecard["comparisons"][0]["summary"]
            self.assertEqual(vessel_score["harnesses"], ["pi"])
            self.assertEqual(vessel_score["attempts_by_tool"], {"fff": 1})
            self.assertEqual(comparison_summary["attempts_by_tool"], {"fff": 1})
            self.assertEqual(scorecard["summary"]["attempts_by_tool"], {"fff": 1})
            self.assertEqual(vessel_score["total_tokens"], 1234)
            self.assertEqual(vessel_score["total_cost"], 0.00123)
            self.assertEqual(scorecard["summary"]["total_cost"], 0.00123)


if __name__ == "__main__":
    unittest.main()
