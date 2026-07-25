import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from tests.benchmark_fixtures import PI_FFF_CONFIG_PATH
from tests.benchmark_fixtures import PI_FFF_PREDICTIONS_PATH
from tests.benchmark_fixtures import write_pi_fff_config
from tests.benchmark_fixtures import write_runtime_snapshot
from tests.benchmark_fixtures import write_vessel_candidate
from tests.benchmark_fixtures import write_vessel_preflight
from tests.benchmark_fixtures import write_vessel_ready_inputs
from tests.preflight_artifacts import write_preflight_artifact
from yacht.workflows.benchmark_launcher_handoff import write_benchmark_launcher_handoff
from yacht.cli import main
from yacht.courses.handoff import write_course_handoff
from yacht.domain.model import ConfigError
from yacht.courses.artifacts import candidate_patches_path
from yacht.runtimes.instances import RUNTIME_INSTANCES_PLAN_PATH
from yacht.courses.swe_bench.grading import write_swe_bench_grading_report
from yacht.courses.swe_bench.predictions import write_swe_bench_predictions


class BenchmarkLauncherHandoffTests(unittest.TestCase):
    def test_launcher_handoff_writes_ready_swe_bench_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_ready_logbook(Path(temp_dir))

            handoff = write_benchmark_launcher_handoff(
                logbook_dir=logbook_dir,
                max_workers=2,
            )

            self.assertEqual(handoff["schema"], "yacht.benchmark-launcher-handoff.v1")
            self.assertEqual(handoff["regatta"], "pi-fff-comparison")
            self.assertEqual(handoff["course"], "swe-bench-lite")
            self.assertEqual(handoff["status"], "ready-to-launch")
            vessel = handoff["comparisons"][0]["vessels"][0]
            self.assertEqual(vessel["name"], "pi-baseline")
            self.assertEqual(vessel["status"], "ready-to-launch")
            self.assertEqual(
                vessel["preflight_artifact_path"],
                str(logbook_dir / "preflight/pi-vs-pi-fff/pi-baseline.json"),
            )
            self.assertTrue(vessel["preflight_artifact_present"])
            self.assertEqual(vessel["preflight_status"], "passed")
            self.assertEqual(
                vessel["command"],
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "yacht.courses.swe_bench.harness",
                    "--predictions",
                    str(
                        logbook_dir
                        / "course-handoff/swe-bench/vessels/pi-baseline/candidate-patches.jsonl"
                    ),
                    "--report-dir",
                    str(
                        logbook_dir
                        / "course-handoff/swe-bench/vessels/pi-baseline/native-report"
                    ),
                    "--dataset",
                    "princeton-nlp/SWE-bench_Lite",
                    "--split",
                    "test",
                    "--run-id",
                    "pi-fff-comparison__pi-vs-pi-fff__pi-baseline",
                    "--vessel",
                    "pi-baseline",
                    "--max-workers",
                    "2",
                    "--instance-ids",
                    "django__django-11099",
                ],
            )
            self.assertEqual(
                vessel["command_preview"],
                "uv run python -m yacht.courses.swe_bench.harness "
                f"--predictions {logbook_dir}/course-handoff/swe-bench/vessels/pi-baseline/candidate-patches.jsonl "
                f"--report-dir {logbook_dir}/course-handoff/swe-bench/vessels/pi-baseline/native-report "
                "--dataset princeton-nlp/SWE-bench_Lite --split test "
                "--run-id pi-fff-comparison__pi-vs-pi-fff__pi-baseline "
                "--vessel pi-baseline --max-workers 2 "
                "--instance-ids django__django-11099",
            )
            self.assertEqual(
                vessel["expected_yacht_grading_report_path"],
                str(
                    logbook_dir
                    / "course-handoff/swe-bench/vessels/pi-baseline/grading-report.json"
                ),
            )
            self.assertEqual(
                vessel["expected_native_report_path"],
                str(
                    logbook_dir
                    / "course-handoff/swe-bench/vessels/pi-baseline/native-report"
                    / "pi-baseline.pi-fff-comparison__pi-vs-pi-fff__pi-baseline.json"
                ),
            )
            saved = json.loads(
                (logbook_dir / "benchmark-launcher-handoff.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(saved, handoff)

    def test_launcher_handoff_includes_all_small_benchmark_instance_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = Path("examples/container-pi-fff-real-benchmark-small.toml")
            logbook_dir = root / "logbook"
            handoff = write_course_handoff(config_path, logbook_dir)
            _write_candidate_patches(
                logbook_dir=logbook_dir,
                handoff=handoff,
                vessel_name="pi-container-baseline",
            )
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                regatta_name="container-pi-fff-real-benchmark-small",
                comparison_name="container-pi-vs-pi-fff-benchmark-small",
                vessel_name="pi-container-baseline",
                status="passed",
            )
            write_runtime_snapshot(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=root / "workspace",
            )

            launcher = write_benchmark_launcher_handoff(
                logbook_dir=logbook_dir,
            )

            command = launcher["comparisons"][0]["vessels"][0]["command"]
            instance_ids_index = command.index("--instance-ids")
            self.assertEqual(
                command[instance_ids_index + 1 :],
                ["django__django-11099", "django__django-11179"],
            )

    def test_launcher_handoff_reports_missing_and_already_graded_vessels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_mixed_logbook(Path(temp_dir))

            handoff = write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            self.assertEqual(handoff["status"], "mixed")
            vessels = handoff["comparisons"][0]["vessels"]
            self.assertEqual(vessels[0]["name"], "pi-baseline")
            self.assertEqual(vessels[0]["status"], "missing-candidate-patches")
            self.assertEqual(vessels[0]["preflight_status"], "missing")
            self.assertNotIn("command", vessels[0])
            self.assertEqual(vessels[1]["name"], "pi-plus-fff")
            self.assertEqual(vessels[1]["status"], "already-graded")
            self.assertNotIn("command", vessels[1])

    def test_launcher_handoff_blocks_candidate_without_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_vessel_candidate(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-baseline",
            )

            handoff = write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            vessel = handoff["comparisons"][0]["vessels"][0]
            self.assertEqual(vessel["name"], "pi-baseline")
            self.assertEqual(vessel["status"], "missing-preflight")
            self.assertFalse(vessel["preflight_artifact_present"])
            self.assertEqual(vessel["preflight_status"], "missing")
            self.assertNotIn("command", vessel)

    def test_launcher_handoff_blocks_candidate_without_runtime_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_vessel_candidate(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-baseline",
            )
            write_vessel_preflight(logbook_dir=logbook_dir, vessel_name="pi-baseline")

            handoff = write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            vessel = handoff["comparisons"][0]["vessels"][0]
            self.assertEqual(vessel["name"], "pi-baseline")
            self.assertEqual(vessel["status"], "missing-runtime-snapshot")
            self.assertEqual(
                vessel["runtime_instances_artifact_path"],
                str(logbook_dir / "runtime-instances.json"),
            )
            self.assertFalse(vessel["runtime_instances_artifact_present"])
            self.assertEqual(vessel["runtime_snapshot_status"], "missing")
            self.assertNotIn("command", vessel)

    def test_launcher_handoff_reports_runtime_snapshot_missing_vessel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            write_pi_fff_config(config_path)
            write_vessel_ready_inputs(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=root / "workspace",
                vessel_name="pi-baseline",
            )
            snapshot_path = logbook_dir / RUNTIME_INSTANCES_PLAN_PATH
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            comparison = snapshot["comparisons"][0]
            comparison["vessels"] = [
                vessel
                for vessel in comparison["vessels"]
                if vessel["name"] != "pi-baseline"
            ]
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    ["internals", "benchmark-launcher", "--logbook", str(logbook_dir)]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: runtime instances artifact "
                "does not contain vessel pi-baseline:",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_launcher_handoff_blocks_failed_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_vessel_candidate(
                config_path=PI_FFF_CONFIG_PATH,
                logbook_dir=logbook_dir,
                vessel_name="pi-baseline",
            )
            write_vessel_preflight(
                logbook_dir=logbook_dir,
                vessel_name="pi-baseline",
                status="failed",
            )

            handoff = write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            vessel = handoff["comparisons"][0]["vessels"][0]
            self.assertEqual(vessel["status"], "preflight-failed")
            self.assertTrue(vessel["preflight_artifact_present"])
            self.assertEqual(vessel["preflight_status"], "failed")
            self.assertNotIn("command", vessel)

    def test_launcher_handoff_command_writes_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_ready_logbook(Path(temp_dir))

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "internals",
                        "benchmark-launcher",
                        "--logbook",
                        str(logbook_dir),
                        "--max-workers",
                        "3",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema"], "yacht.benchmark-launcher-handoff.v1")
            self.assertEqual(payload["status"], "ready-to-launch")
            command = payload["comparisons"][0]["vessels"][0]["command"]
            self.assertEqual(command[:3], ["uv", "run", "python"])
            self.assertIn("yacht.courses.swe_bench.harness", command)
            self.assertIn("--max-workers", command)
            self.assertIn("3", command)
            self.assertTrue((logbook_dir / "benchmark-launcher-handoff.json").is_file())

    def test_launcher_handoff_command_reports_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "internals",
                        "benchmark-launcher",
                        "--logbook",
                        str(Path(temp_dir) / "logbook"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: course handoff artifact not found",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_launcher_handoff_requires_handoff_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"

            with self.assertRaisesRegex(
                ConfigError,
                "course handoff artifact not found",
            ):
                write_benchmark_launcher_handoff(logbook_dir=logbook_dir)

            self.assertFalse((logbook_dir / "benchmark-launcher-handoff.json").exists())


def _prepared_ready_logbook(root: Path) -> Path:
    logbook_dir = root / "logbook"
    write_vessel_candidate(
        config_path=PI_FFF_CONFIG_PATH,
        logbook_dir=logbook_dir,
        vessel_name="pi-baseline",
    )
    write_runtime_snapshot(
        config_path=PI_FFF_CONFIG_PATH,
        logbook_dir=logbook_dir,
        workspace_path=root / "workspace",
    )
    write_vessel_preflight(logbook_dir=logbook_dir, vessel_name="pi-baseline")
    write_swe_bench_predictions(
        config_path=PI_FFF_CONFIG_PATH,
        predictions_path=PI_FFF_PREDICTIONS_PATH,
        logbook_dir=logbook_dir,
        vessel_name="pi-plus-fff",
    )
    write_vessel_preflight(logbook_dir=logbook_dir, vessel_name="pi-plus-fff")
    return logbook_dir


def _prepared_mixed_logbook(root: Path) -> Path:
    logbook_dir = root / "logbook"
    write_course_handoff(PI_FFF_CONFIG_PATH, logbook_dir)
    write_swe_bench_predictions(
        config_path=PI_FFF_CONFIG_PATH,
        predictions_path=PI_FFF_PREDICTIONS_PATH,
        logbook_dir=logbook_dir,
        vessel_name="pi-plus-fff",
    )
    write_swe_bench_grading_report(
        config_path=PI_FFF_CONFIG_PATH,
        native_report_path=Path("examples/pi-fff-native-report.json"),
        logbook_dir=logbook_dir,
        vessel_name="pi-plus-fff",
    )
    return logbook_dir


def _write_candidate_patches(
    *,
    logbook_dir: Path,
    handoff: dict[str, Any],
    vessel_name: str,
) -> None:
    path = candidate_patches_path(
        logbook_dir=logbook_dir,
        handoff=handoff,
        vessel_name=vessel_name,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "instance_id": str(task["id"]),
            "model_name_or_path": vessel_name,
            "model_patch": (
                "diff --git a/example.py b/example.py\n"
                "--- a/example.py\n"
                "+++ b/example.py\n"
            ),
        }
        for task in handoff["tasks"]
    ]
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
