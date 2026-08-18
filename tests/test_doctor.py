import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.fixtures import create_fixture_repo, hermetic_swe_bench_config
from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.cli import main
from yacht.preflight.execution import CommandResult
from yacht.workflows.doctor import render_doctor_report, run_doctor

CONTAINER_CONFIG = """
[regatta]
name = "doctor-container"

[course]
name = "tiny-course"
tasks = [
  { id = "task-1", title = "Fix a failing test", difficulty = 1 },
]

[secrets.anthropic]
source = "env"
name = "ANTHROPIC_API_KEY"

[runtimes.box]
backend = "container"
image = "yacht/test-image:1"
command = ["agent"]
required_secrets = ["anthropic"]

[[vessels]]
name = "baseline"
model = "mock"
runtime = "box"
"""


def _ok_runner(argv):
    return CommandResult(exit_code=0, stdout="27.0.1\n", stderr="")


def _fail_runner(argv):
    return CommandResult(exit_code=1, stdout="", stderr="cannot connect")


def _which_all(name):
    return f"/usr/bin/{name}"


class RunDoctorTests(unittest.TestCase):
    def test_passes_when_all_host_checks_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_doctor(
                config_path=None,
                logbook_dir=Path(temp_dir) / "logbook",
                which=_which_all,
                command_runner=_ok_runner,
                env={},
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["failed"], [])
        names = [check["name"] for check in report["checks"]]
        self.assertEqual(
            names,
            [
                "python",
                "uv",
                "git",
                "docker",
                "docker-daemon",
                "logbook-path",
                "swebench-harness",
            ],
        )

    def test_fails_and_hints_when_docker_daemon_is_down(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_doctor(
                config_path=None,
                logbook_dir=Path(temp_dir) / "logbook",
                check_swebench=False,
                which=_which_all,
                command_runner=_fail_runner,
                env={},
            )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failed"], ["docker-daemon"])
        daemon = _check_by_name(report, "docker-daemon")
        self.assertIn("cannot connect", daemon["detail"])
        self.assertIn("start Docker", daemon["hint"])

    def test_skips_daemon_check_when_docker_cli_is_missing(self) -> None:
        def which(name):
            return None if name == "docker" else f"/usr/bin/{name}"

        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_doctor(
                config_path=None,
                logbook_dir=Path(temp_dir) / "logbook",
                check_swebench=False,
                which=which,
                command_runner=_ok_runner,
                env={},
            )

        self.assertEqual(report["failed"], ["docker"])
        self.assertEqual(_check_by_name(report, "docker-daemon")["status"], "skipped")

    def test_fails_when_logbook_path_is_not_writable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            blocker = Path(temp_dir) / "blocker"
            blocker.write_text("file, not a directory", encoding="utf-8")

            report = run_doctor(
                config_path=None,
                logbook_dir=blocker / "logbook",
                check_swebench=False,
                which=_which_all,
                command_runner=_ok_runner,
                env={},
            )

        self.assertIn("logbook-path", report["failed"])
        self.assertIn("--logbook", _check_by_name(report, "logbook-path")["hint"])

    def test_skip_swebench_omits_the_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_doctor(
                config_path=None,
                logbook_dir=Path(temp_dir) / "logbook",
                check_swebench=False,
                which=_which_all,
                command_runner=_ok_runner,
                env={},
            )

        names = [check["name"] for check in report["checks"]]
        self.assertNotIn("swebench-harness", names)

    def test_config_checks_report_image_and_secret_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(CONTAINER_CONFIG, encoding="utf-8")

            report = run_doctor(
                config_path=config_path,
                logbook_dir=Path(temp_dir) / "logbook",
                check_swebench=False,
                which=_which_all,
                command_runner=_fail_runner,
                env={},
            )

        self.assertEqual(_check_by_name(report, "config")["status"], "passed")
        image = _check_by_name(report, "runtime-image:box")
        self.assertEqual(image["status"], "failed")
        self.assertIn("docker build", image["hint"])
        secret = _check_by_name(report, "secret:anthropic")
        self.assertEqual(secret["status"], "warning")
        self.assertIn("export ANTHROPIC_API_KEY", secret["hint"])
        self.assertEqual(report["warnings"], ["secret:anthropic"])

    def test_config_checks_pass_with_image_and_secret_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(CONTAINER_CONFIG, encoding="utf-8")

            report = run_doctor(
                config_path=config_path,
                logbook_dir=Path(temp_dir) / "logbook",
                check_swebench=False,
                which=_which_all,
                command_runner=_ok_runner,
                env={"ANTHROPIC_API_KEY": "value"},
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["warnings"], [])
        self.assertEqual(_check_by_name(report, "secret:anthropic")["status"], "passed")

    def test_invalid_config_fails_with_validate_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text("[regatta]\n", encoding="utf-8")

            report = run_doctor(
                config_path=config_path,
                logbook_dir=Path(temp_dir) / "logbook",
                check_swebench=False,
                which=_which_all,
                command_runner=_ok_runner,
                env={},
            )

        config = _check_by_name(report, "config")
        self.assertEqual(config["status"], "failed")
        self.assertIn("yacht validate", config["hint"])

    def test_doctor_accepts_real_example_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = create_fixture_repo(root / "repo")
            config_path = root / "regatta.toml"
            config_path.write_text(
                hermetic_swe_bench_config(PI_WITH_FFF_CONFIG, repo),
                encoding="utf-8",
            )

            report = run_doctor(
                config_path=config_path,
                logbook_dir=root / "logbook",
                check_swebench=False,
                which=_which_all,
                command_runner=_ok_runner,
                env={"ANTHROPIC_API_KEY": "value"},
            )

        self.assertEqual(report["status"], "passed")

    def test_omp_and_codex_runtime_smokes_inspect_repo_owned_images(self) -> None:
        inspected: list[str] = []

        def runner(argv):
            if argv[:3] == ("docker", "image", "inspect"):
                inspected.append(argv[3])
            return _ok_runner(argv)

        with tempfile.TemporaryDirectory() as temp_dir:
            for config in (
                Path("examples/container-omp-runtime-smoke.toml"),
                Path("examples/container-codex-runtime-smoke.toml"),
            ):
                report = run_doctor(
                    config_path=config,
                    logbook_dir=Path(temp_dir) / "logbook",
                    check_swebench=False,
                    which=_which_all,
                    command_runner=runner,
                    env={},
                )
                self.assertEqual(report["status"], "passed")

        self.assertEqual(
            inspected,
            [
                "yacht/omp-runtime:omp-17.2.15",
                "yacht/codex-runtime:codex-0.147.0",
            ],
        )


class DoctorRenderingTests(unittest.TestCase):
    def test_text_report_shows_status_markers_and_hints(self) -> None:
        report = {
            "status": "failed",
            "failed": ["docker-daemon"],
            "warnings": ["secret:anthropic"],
            "checks": [
                {"name": "uv", "status": "passed", "detail": "/usr/bin/uv"},
                {
                    "name": "docker-daemon",
                    "status": "failed",
                    "detail": "docker info failed",
                    "hint": "start Docker and re-run yacht doctor",
                },
                {
                    "name": "secret:anthropic",
                    "status": "warning",
                    "detail": "$ANTHROPIC_API_KEY is not set",
                    "hint": "export ANTHROPIC_API_KEY",
                },
            ],
        }

        rendered = render_doctor_report(report)

        self.assertIn("YACHT doctor: failed", rendered)
        self.assertIn("[pass] uv: /usr/bin/uv", rendered)
        self.assertIn("[FAIL] docker-daemon: docker info failed", rendered)
        self.assertIn("hint: start Docker and re-run yacht doctor", rendered)
        self.assertIn("[warn] secret:anthropic", rendered)

    def test_cli_exit_code_reflects_report_status(self) -> None:
        failed_report = {
            "status": "failed",
            "failed": ["uv"],
            "warnings": [],
            "checks": [],
        }
        with (
            patch(
                "yacht.cli.commands.doctor.run_doctor",
                return_value=failed_report,
            ),
            redirect_stdout(StringIO()),
        ):
            exit_code = main(["doctor"])

        self.assertEqual(exit_code, 1)


def _check_by_name(report, name):
    for check in report["checks"]:
        if check["name"] == name:
            return check
    raise AssertionError(f"no check named {name} in {report['checks']}")


if __name__ == "__main__":
    unittest.main()
