import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import (
    ConfigError,
    Course,
    PreflightCheck,
    Regatta,
    RuntimeInstance,
    RuntimeRecipe,
    Vessel,
)
from yacht.preflight.execution import (
    EffectiveCheck,
    _agent_response_contract,
    _execute_check,
    _execute_path_isolation_check,
    _run_command,
    execute_preflight,
)


class RunCommandTests(unittest.TestCase):
    def test_runs_real_subprocess_and_captures_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = _run_command(
                ("python3", "-c", "import sys; print('out'); sys.exit(3)"),
                {"PATH": "/usr/bin:/bin:/usr/local/bin"},
                Path(temp_dir),
            )

        self.assertEqual(result.exit_code, 3)
        self.assertIn("out", result.stdout)
        self.assertEqual(result.stderr, "")


class ExecuteCheckTests(unittest.TestCase):
    def test_rejects_unsupported_check_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            instance = _instance(Path(temp_dir), env={})
            vessel = Vessel(
                name="baseline",
                model="mock",
                rigging=(),
                runtime="host",
            )
            regatta = Regatta(
                name="bad-check",
                course=Course(name="tiny-course", tasks=()),
                vessels=(vessel,),
                runtime_recipes={"host": instance.runtime},
            )

            with self.assertRaisesRegex(
                ValueError, "unsupported preflight check kind bogus"
            ):
                _execute_check(
                    _effective_check(PreflightCheck(name="bad", kind="bogus")),
                    instance,
                    command_runner=lambda argv, env, cwd: None,
                    agent_prompt_runner=None,
                    regatta=regatta,
                    vessel=vessel,
                )

    def test_path_isolation_fails_for_paths_outside_trial_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _instance(
                root,
                env={"HOME": str(root / "home"), "XDG_CACHE_HOME": "/tmp/outside"},
            )
            check = PreflightCheck(
                name="isolated",
                kind="path-isolation",
                env=("HOME", "XDG_CACHE_HOME"),
            )

            result = _execute_path_isolation_check(_effective_check(check), instance)

        self.assertEqual(result["status"], "failed")
        evidence = result["evidence"]
        self.assertEqual(
            evidence["outside_trial_home"], {"XDG_CACHE_HOME": "/tmp/outside"}
        )
        self.assertNotIn("missing_env", evidence)

    def test_path_isolation_fails_for_missing_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _instance(root, env={"HOME": str(root / "home")})
            check = PreflightCheck(
                name="isolated",
                kind="path-isolation",
                env=("HOME", "XDG_STATE_HOME"),
            )

            result = _execute_path_isolation_check(_effective_check(check), instance)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["evidence"]["missing_env"], ["XDG_STATE_HOME"])

    def test_path_isolation_passes_inside_trial_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _instance(
                root,
                env={
                    "HOME": str(root / "home"),
                    "XDG_CACHE_HOME": str(root / "home" / ".cache"),
                },
            )
            check = PreflightCheck(
                name="isolated",
                kind="path-isolation",
                env=("HOME", "XDG_CACHE_HOME"),
            )

            result = _execute_path_isolation_check(_effective_check(check), instance)

        self.assertEqual(result["status"], "passed")


class ExecutePreflightTests(unittest.TestCase):
    def test_rejects_vessel_without_any_preflight_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _instance(root, env={})
            vessel = Vessel(
                name="baseline",
                model="mock",
                rigging=(),
                runtime="host",
            )
            regatta = Regatta(
                name="no-checks",
                course=Course(name="tiny-course", tasks=()),
                vessels=(vessel,),
                runtime_recipes={"host": instance.runtime},
            )

            with self.assertRaisesRegex(
                ConfigError,
                "vessel baseline has no preflight checks",
            ):
                execute_preflight(
                    regatta=regatta,
                    vessel=vessel,
                    instance=instance,
                    artifact_path=root / "preflight.json",
                )
            self.assertFalse((root / "preflight.json").exists())


class AgentResponseContractTests(unittest.TestCase):
    def test_rejects_non_json_response(self) -> None:
        contract = _agent_response_contract("this is not json")

        self.assertIsNone(contract.response_json)
        self.assertEqual(contract.errors, ["response must be a JSON object"])

    def test_rejects_unavailable_or_unconfigured_agent(self) -> None:
        contract = _agent_response_contract('{"available": false, "configured": false}')

        self.assertEqual(
            contract.errors,
            [
                "response.available must be true",
                "response.configured must be true",
            ],
        )

    def test_accepts_available_configured_response(self) -> None:
        contract = _agent_response_contract('{"available": true, "configured": true}')

        self.assertEqual(contract.errors, [])
        self.assertIsNotNone(contract.response_json)


def _instance(root: Path, *, env: dict[str, str]) -> RuntimeInstance:
    runtime = RuntimeRecipe(name="host", backend="host-nix", command=("agent",))
    return RuntimeInstance(
        runtime=runtime,
        temp_home=root / "home",
        workspace_path=root / "workspace",
        env=env,
        command_prefix=(),
        cleanup_paths=(),
    )


def _effective_check(check: PreflightCheck) -> EffectiveCheck:
    return EffectiveCheck(
        check=check,
        required=True,
        origin="runtime",
        origin_name="host",
    )


if __name__ == "__main__":
    unittest.main()
