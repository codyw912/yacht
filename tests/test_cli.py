import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from tests.fixtures import INVALID_REGATTA_CONFIG, REGATTA_CONFIG
from yacht.cli import main


@dataclass(frozen=True)
class CliResult:
    exit_code: int
    stdout: str
    stderr: str
    logbook_exists: bool
    scorecard_exists: bool


def run_cli_with_config(config: str, args: list[str]) -> CliResult:
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        config_path = workspace / "regatta.toml"
        logbook_dir = workspace / "logbook"
        config_path.write_text(config, encoding="utf-8")
        replacements = {
            "{config}": str(config_path),
            "{logbook}": str(logbook_dir),
        }
        resolved_args = [replacements.get(arg, arg) for arg in args]

        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(resolved_args)

        logbook_exists = logbook_dir.exists()
        scorecard_exists = (logbook_dir / "scorecard.json").exists()

    return CliResult(
        exit_code=exit_code,
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
        logbook_exists=logbook_exists,
        scorecard_exists=scorecard_exists,
    )


class CliTests(unittest.TestCase):
    def test_run_prints_scorecard_summary(self) -> None:
        result = run_cli_with_config(
            REGATTA_CONFIG,
            ["run", "{config}", "--logbook", "{logbook}"],
        )

        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.scorecard_exists)
        self.assertIn('"regatta": "memory-smoke-test"', result.stdout)

    def test_run_prints_config_errors_without_traceback(self) -> None:
        result = run_cli_with_config(
            INVALID_REGATTA_CONFIG,
            ["run", "{config}", "--logbook", "{logbook}"],
        )

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn(
            "error: invalid regatta config: course.tasks must contain at least one task",
            result.stderr,
        )
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(result.logbook_exists)

    def test_validate_prints_valid_regatta_name(self) -> None:
        result = run_cli_with_config(REGATTA_CONFIG, ["validate", "{config}"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, "valid regatta config: memory-smoke-test\n")
        self.assertEqual(result.stderr, "")

    def test_validate_prints_config_errors_without_traceback(self) -> None:
        result = run_cli_with_config(INVALID_REGATTA_CONFIG, ["validate", "{config}"])

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn(
            "error: invalid regatta config: course.tasks must contain at least one task",
            result.stderr,
        )
        self.assertNotIn("Traceback", result.stderr)

    def test_validate_json_prints_machine_readable_success(self) -> None:
        result = run_cli_with_config(
            REGATTA_CONFIG,
            ["validate", "{config}", "--format", "json"],
        )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            json.loads(result.stdout),
            {
                "valid": True,
                "regatta": "memory-smoke-test",
            },
        )

    def test_validate_json_prints_machine_readable_error(self) -> None:
        result = run_cli_with_config(
            INVALID_REGATTA_CONFIG,
            ["validate", "{config}", "--format", "json"],
        )

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            json.loads(result.stdout),
            {
                "valid": False,
                "error": "course.tasks must contain at least one task",
            },
        )


if __name__ == "__main__":
    unittest.main()
