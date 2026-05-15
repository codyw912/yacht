import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.benchmark_fixtures import PI_FFF_CONFIG_PATH
from yacht.regatta import (
    Comparison,
    ConfigError,
    Metrics,
    Regatta,
    RuntimeInstance,
    RuntimeRecipe,
    Task,
    Vessel,
    load_regatta,
)
from yacht.cli import main
from yacht.swebench_predictions_from_attempts import (
    write_swe_bench_predictions_from_attempts,
)
from yacht.task_attempt_runner import _task_prompt
from yacht.task_attempts import AgentTaskResult, write_task_attempt


MODEL_PATCH = (
    "diff --git a/example.py b/example.py\n"
    "--- a/example.py\n"
    "+++ b/example.py\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
)


class SweBenchPredictionsFromAttemptsTests(unittest.TestCase):
    def test_writes_vessel_candidate_patches_from_completed_task_attempts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            _write_attempt(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-plus-fff",
                response=json.dumps({"model_patch": MODEL_PATCH}),
            )

            summary = write_swe_bench_predictions_from_attempts(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-plus-fff",
            )

            self.assertEqual(summary["status"], "validated")
            self.assertEqual(summary["vessel"], "pi-plus-fff")
            self.assertEqual(summary["prediction_count"], 1)
            candidate_path = (
                logbook_dir
                / "course-handoff/swe-bench/vessels/pi-plus-fff/candidate-patches.jsonl"
            )
            self.assertEqual(summary["candidate_patches_path"], str(candidate_path))
            self.assertEqual(
                json.loads(candidate_path.read_text(encoding="utf-8")),
                {
                    "instance_id": "django__django-11099",
                    "model_name_or_path": "pi-plus-fff",
                    "model_patch": MODEL_PATCH,
                },
            )

    def test_predictions_from_attempts_command_writes_candidate_patches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            _write_attempt(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-plus-fff",
                response=json.dumps({"model_patch": MODEL_PATCH}),
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "predictions-from-attempts",
                        str(PI_FFF_CONFIG_PATH),
                        "--logbook",
                        str(logbook_dir),
                        "--vessel",
                        "pi-plus-fff",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "validated")
            self.assertEqual(payload["vessel"], "pi-plus-fff")
            self.assertEqual(payload["prediction_count"], 1)

    def test_extracts_model_patch_from_fenced_json_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            _write_attempt(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-plus-fff",
                response=(
                    "The fix has been applied.\n\n"
                    "```json\n"
                    f"{json.dumps({'model_patch': MODEL_PATCH})}\n"
                    "```\n"
                ),
            )

            summary = write_swe_bench_predictions_from_attempts(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-plus-fff",
            )

            self.assertEqual(summary["status"], "validated")
            candidate_path = Path(summary["candidate_patches_path"])
            self.assertEqual(
                json.loads(candidate_path.read_text(encoding="utf-8"))[
                    "model_patch"
                ],
                MODEL_PATCH,
            )

    def test_swe_bench_task_prompt_requests_model_patch_json(self) -> None:
        regatta = load_regatta(PI_FFF_CONFIG_PATH)

        prompt = _task_prompt(
            regatta,
            regatta.vessels[0],
            regatta.course.tasks[0],
        )

        self.assertIn("SWE-bench", prompt)
        self.assertIn("model_patch", prompt)
        self.assertIn("JSON object", prompt)

    def test_rejects_task_attempt_response_without_model_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"
            _write_attempt(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-plus-fff",
                response=json.dumps({"completed": True}),
            )

            with self.assertRaisesRegex(
                ConfigError,
                "response must be a JSON object with non-empty model_patch",
            ):
                write_swe_bench_predictions_from_attempts(
                    config_path=PI_FFF_CONFIG_PATH,
                    logbook_dir=logbook_dir,
                    vessel_name="pi-plus-fff",
                )


def _write_attempt(
    *,
    config_path: Path,
    logbook_dir: Path,
    vessel_name: str,
    response: str,
) -> None:
    regatta = load_regatta(config_path)
    comparison = regatta.comparisons[0]
    vessel = _vessel(regatta, vessel_name)
    task = regatta.course.tasks[0]
    artifact_path = (
        logbook_dir
        / "task-attempts"
        / comparison.name
        / vessel.name
        / f"{task.id}.json"
    )
    transcript_path = (
        logbook_dir
        / "transcripts"
        / comparison.name
        / vessel.name
        / "tasks"
        / f"{task.id}.json"
    )
    runtime = RuntimeRecipe(
        name="pi",
        backend="host-nix",
        command=("pi",),
    )
    instance = RuntimeInstance(
        runtime=runtime,
        temp_home=logbook_dir / "runtime/home",
        workspace_path=logbook_dir / "workspace",
        env={"HOME": str(logbook_dir / "runtime/home")},
        command_prefix=(),
        cleanup_paths=(logbook_dir / "runtime",),
    )
    write_task_attempt(
        artifact_path=artifact_path,
        regatta=regatta,
        comparison=Comparison(
            name=comparison.name,
            course=comparison.course,
            vessels=comparison.vessels,
        ),
        vessel=vessel,
        task=Task(id=task.id, title=task.title, difficulty=task.difficulty),
        instance=instance,
        prompt="Solve the task.",
        result=AgentTaskResult(
            exit_code=0,
            response=response,
            tool_calls=(),
            transcript_path=transcript_path,
            metrics=Metrics(tokens=100, duration_seconds=1.0),
        ),
    )


def _vessel(regatta: Regatta, vessel_name: str) -> Vessel:
    for vessel in regatta.vessels:
        if vessel.name == vessel_name:
            return vessel
    raise AssertionError(f"missing vessel {vessel_name}")


if __name__ == "__main__":
    unittest.main()
