import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.test_benchmark_aggregate import _write_logbook
from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.cli import main
from yacht.real_benchmark_repetitions import run_real_benchmark_repetitions
from yacht.regatta import ConfigError


class RealBenchmarkRepetitionsTests(unittest.TestCase):
    def test_runs_repetitions_into_child_logbooks_and_writes_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path = root / "workspace"
            workspace_path.mkdir()
            logbook_dir = root / "series"
            child_logbooks = []

            def eval_runner(child_logbook: Path) -> dict[str, object]:
                child_logbooks.append(child_logbook)
                resolved = 1 if child_logbook.name == "run-001" else 0
                _write_logbook(
                    child_logbook,
                    baseline_resolved=resolved,
                    fff_resolved=1,
                )
                return {
                    "status": "complete",
                    "regatta": "pi-fff-comparison",
                    "course": "swe-bench-lite",
                }

            summary = run_real_benchmark_repetitions(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=workspace_path,
                secret_values={},
                repetitions=2,
                eval_runner=eval_runner,
            )

            self.assertEqual(summary["schema"], "yacht.real-benchmark-repetitions.v1")
            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["summary"]["repetitions"], 2)
            self.assertEqual(summary["summary"]["completed_runs"], 2)
            self.assertEqual(
                child_logbooks,
                [logbook_dir / "runs/run-001", logbook_dir / "runs/run-002"],
            )
            self.assertTrue((logbook_dir / "real-benchmark-repetitions.json").is_file())
            self.assertTrue((logbook_dir / "benchmark-aggregate.json").is_file())
            aggregate = summary["aggregate"]
            self.assertEqual(aggregate["run_count"], 2)
            self.assertEqual(
                aggregate["comparisons"][0]["delta"]["resolved_instances_delta"],
                1,
            )

    def test_aggregates_completed_repetitions_when_one_child_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            logbook_dir = root / "series"

            def eval_runner(child_logbook: Path) -> dict[str, object]:
                if child_logbook.name == "run-001":
                    _write_logbook(
                        child_logbook,
                        baseline_resolved=1,
                        fff_resolved=1,
                    )
                    return {"status": "complete"}
                child_logbook.mkdir(parents=True)
                return {"status": "blocked"}

            summary = run_real_benchmark_repetitions(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=root,
                secret_values={},
                repetitions=2,
                eval_runner=eval_runner,
            )

            self.assertEqual(summary["status"], "partial")
            self.assertEqual(summary["summary"]["completed_runs"], 1)
            self.assertEqual(summary["summary"]["failed_runs"], 1)
            self.assertEqual(summary["aggregate"]["run_count"], 1)

    def test_requires_positive_repetitions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text('name = "empty"\n', encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "real benchmark repetitions must be at least 1",
            ):
                run_real_benchmark_repetitions(
                    config_path=config_path,
                    logbook_dir=root / "series",
                    workspace_path=root,
                    secret_values={},
                    repetitions=0,
                    eval_runner=lambda _logbook: {"status": "complete"},
                )

    def test_requires_fresh_child_logbooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            logbook_dir = root / "series"
            (logbook_dir / "runs/run-001").mkdir(parents=True)

            with self.assertRaisesRegex(
                ConfigError,
                "repetition child logbook already exists",
            ):
                run_real_benchmark_repetitions(
                    config_path=config_path,
                    logbook_dir=logbook_dir,
                    workspace_path=root,
                    secret_values={},
                    repetitions=1,
                    eval_runner=lambda _logbook: {"status": "complete"},
                )

    def test_command_reports_config_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text('name = "empty"\n', encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()

            with patch(
                "yacht.cli.run_real_benchmark_repetitions",
                side_effect=ConfigError("boom"),
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "real-benchmark-repetitions",
                        str(config_path),
                        "--logbook",
                        str(root / "series"),
                        "--workspace",
                        str(root),
                        "--repetitions",
                        "2",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("error: invalid regatta config: boom", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
