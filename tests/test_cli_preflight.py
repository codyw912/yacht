import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.cli import main


PASSING_PREFLIGHT_CONFIG = """
[regatta]
name = "cli-preflight"

[preflight]
failure_policy = "abort-group"

[course]
name = "tiny-course"
tasks = [
  { id = "task-1", title = "Fix a failing test", difficulty = 1 },
]

[secrets.token]
source = "env"
name = "YACHT_TEST_TOKEN"

[runtimes.mock]
backend = "host-nix"
flake = "github:example/yacht-runtimes#mock"
command = ["mock-agent"]
required_secrets = ["token"]

[runtimes.mock.preflight]
required = true
checks = [
  { name = "runtime-home-isolated", kind = "path-isolation", env = ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"] },
]

[[vessels]]
name = "baseline"
model = "mock"
runtime = "mock"

[[vessels]]
name = "rigged"
model = "mock"
runtime = "mock"

[[comparisons]]
name = "baseline-vs-rigged"
course = "tiny-course"
vessels = ["baseline", "rigged"]
"""


FAILING_PREFLIGHT_CONFIG = PASSING_PREFLIGHT_CONFIG + """
[riggings.bad-path.env]
BAD_CACHE = "/tmp/yacht-shared-cache"

[riggings.bad-path.preflight]
required = true
checks = [
  { name = "bad-cache-isolated", kind = "path-isolation", env = ["BAD_CACHE"] },
]
"""


class CliPreflightTests(unittest.TestCase):
    def test_preflight_writes_artifacts_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, logbook_dir = _run_preflight(PASSING_PREFLIGHT_CONFIG, Path(temp_dir))

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stderr, "")
            self.assertFalse((logbook_dir / "scorecard.json").exists())
            summary = json.loads(result.stdout)
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(
                summary["comparisons"][0],
                {
                    "name": "baseline-vs-rigged",
                    "status": "passed",
                    "vessels": [
                        {"name": "baseline", "status": "passed"},
                        {"name": "rigged", "status": "passed"},
                    ],
                },
            )

            artifact_path = (
                logbook_dir
                / "preflight"
                / "baseline-vs-rigged"
                / "baseline.json"
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["status"], "passed")
            self.assertEqual(artifact["comparison"], "baseline-vs-rigged")
            self.assertEqual(artifact["secret_refs"][0]["redacted"], True)

    def test_preflight_applies_abort_group_status_without_running_tasks(self) -> None:
        config = FAILING_PREFLIGHT_CONFIG.replace(
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"',
            'name = "rigged"\nmodel = "mock"\nruntime = "mock"\nrigging = ["bad-path"]',
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result, logbook_dir = _run_preflight(config, Path(temp_dir))

            self.assertEqual(result.exit_code, 1)
            self.assertEqual(result.stderr, "")
            self.assertFalse((logbook_dir / "scorecard.json").exists())
            summary = json.loads(result.stdout)
            self.assertEqual(summary["status"], "invalid")
            self.assertEqual(summary["comparisons"][0]["status"], "invalid")
            self.assertEqual(
                summary["comparisons"][0]["vessels"],
                [
                    {"name": "baseline", "status": "passed"},
                    {"name": "rigged", "status": "failed"},
                ],
            )

            artifact_path = (
                logbook_dir
                / "preflight"
                / "baseline-vs-rigged"
                / "rigged.json"
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["status"], "failed")


class CliResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


def _run_preflight(config: str, root: Path) -> tuple[CliResult, Path]:
    config_path = root / "regatta.toml"
    logbook_dir = root / "logbook"
    workspace_dir = root / "workspace"
    config_path.write_text(config, encoding="utf-8")
    workspace_dir.mkdir()

    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = main(
            [
                "preflight",
                str(config_path),
                "--logbook",
                str(logbook_dir),
                "--workspace",
                str(workspace_dir),
                "--secret",
                "token=test-secret",
            ]
        )

    result = CliResult(exit_code, stdout.getvalue(), stderr.getvalue())
    return result, logbook_dir


if __name__ == "__main__":
    unittest.main()
