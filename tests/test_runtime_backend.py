import os
import tempfile
import unittest
from pathlib import Path

from tests.test_provisioning import CONTAINER_PI_CONFIG, PI_WITH_FFF_CONFIG
from yacht.host_nix_runtime import resolve_host_nix_runtime
from yacht.regatta import load_regatta
from yacht.runtime_backend import (
    ContainerRuntimeBackend,
    HostNixRuntimeBackend,
    RuntimePreparationError,
    SetupProcessResult,
)


class HostNixRuntimeBackendTests(unittest.TestCase):
    def test_resolver_provides_host_nix_env_for_dry_run_and_prepare(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            instance_root = root / "trial" / "pi-plus-fff"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            regatta = load_regatta(config_path)
            vessel = regatta.vessels[1]

            resolution = resolve_host_nix_runtime(
                regatta=regatta,
                vessel=vessel,
                instance_root=instance_root,
                workspace_path=workspace_path,
            )

            self.assertEqual(resolution.runtime.name, "pi")
            self.assertEqual(
                resolution.env["PATH"],
                f"{instance_root / 'home' / '.local' / 'state' / 'npm-global' / 'bin'}:"
                f"{os.environ['PATH']}",
            )
            self.assertEqual(
                resolution.env["NPM_CONFIG_PREFIX"],
                str(instance_root / "home" / ".local" / "state" / "npm-global"),
            )
            self.assertEqual(resolution.env["MISE_NO_CONFIG"], "1")
            self.assertEqual(resolution.temp_home, instance_root / "home")
            self.assertEqual(
                resolution.command_prefix,
                ("nix", "develop", "path:.#pi", "--command"),
            )
            self.assertEqual(resolution.command, ("pi",))
            self.assertEqual(resolution.cleanup_paths, (instance_root,))
            self.assertEqual(
                resolution.env["FFF_HISTORY_DB"],
                str(instance_root / "home" / ".local" / "state" / "fff-history.sqlite"),
            )
            self.assertEqual(
                resolution.env_with_secret_placeholders(regatta)["ANTHROPIC_API_KEY"],
                "{secret:anthropic}",
            )
            self.assertEqual(
                resolution.env_with_secret_values(
                    regatta,
                    {"anthropic": "test-secret"},
                )["ANTHROPIC_API_KEY"],
                "test-secret",
            )
            self.assertFalse(instance_root.exists())

    def test_prepare_creates_isolated_runtime_instance_with_explicit_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            trial_root = root / "trial"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path.mkdir()
            regatta = load_regatta(config_path)
            vessel = regatta.vessels[1]

            instance = HostNixRuntimeBackend(setup_runner=_passing_setup).prepare(
                regatta=regatta,
                vessel=vessel,
                trial_root=trial_root,
                workspace_path=workspace_path,
                secret_values={"anthropic": "test-secret"},
            )

            self.assertEqual(instance.runtime.name, "pi")
            self.assertEqual(instance.workspace_path, workspace_path)
            self.assertEqual(
                instance.command_prefix,
                ("nix", "develop", "path:.#pi", "--command"),
            )
            self.assertEqual(instance.env["ANTHROPIC_API_KEY"], "test-secret")
            self.assertEqual(
                instance.env["PATH"],
                f"{instance.temp_home / '.local' / 'state' / 'npm-global' / 'bin'}:"
                f"{os.environ['PATH']}",
            )
            self.assertEqual(instance.env["HOME"], str(instance.temp_home))
            self.assertEqual(
                instance.env["NPM_CONFIG_PREFIX"],
                str(instance.temp_home / ".local" / "state" / "npm-global"),
            )
            self.assertEqual(
                instance.env["NPM_CONFIG_CACHE"],
                str(instance.temp_home / ".cache" / "npm"),
            )
            self.assertEqual(instance.env["MISE_NO_CONFIG"], "1")
            self.assertEqual(instance.env["MISE_NO_ENV"], "1")
            self.assertEqual(instance.env["MISE_NO_HOOKS"], "1")
            self.assertEqual(
                instance.env["XDG_CONFIG_HOME"],
                str(instance.temp_home / ".config"),
            )
            self.assertEqual(
                instance.env["XDG_CACHE_HOME"],
                str(instance.temp_home / ".cache"),
            )
            self.assertEqual(
                instance.env["XDG_STATE_HOME"],
                str(instance.temp_home / ".local" / "state"),
            )
            self.assertEqual(instance.env["PI_FFF_MODE"], "required")
            self.assertEqual(
                instance.env["FFF_HISTORY_DB"],
                str(instance.temp_home / ".local" / "state" / "fff-history.sqlite"),
            )
            self.assertTrue(instance.temp_home.is_dir())
            self.assertTrue((instance.temp_home / ".config").is_dir())
            self.assertTrue((instance.temp_home / ".cache").is_dir())
            self.assertTrue((instance.temp_home / ".cache" / "npm").is_dir())
            self.assertTrue((instance.temp_home / ".local" / "state").is_dir())
            self.assertTrue(
                (instance.temp_home / ".local" / "state" / "npm-global" / "bin")
                .is_dir()
            )
            self.assertEqual(instance.cleanup_paths, (trial_root / "pi-plus-fff",))
            self.assertEqual(len(instance.setup_results), 1)
            self.assertEqual(instance.setup_results[0].target, "npm:@ff-labs/pi-fff")

    def test_prepare_applies_rigging_install_steps_inside_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            trial_root = root / "trial"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path.mkdir()
            regatta = load_regatta(config_path)
            calls = []

            def setup_runner(
                argv: tuple[str, ...],
                env: dict[str, str],
                cwd: Path,
            ) -> SetupProcessResult:
                calls.append((argv, env, cwd))
                return SetupProcessResult(
                    exit_code=0,
                    stdout="installed\n",
                    stderr="",
                )

            instance = HostNixRuntimeBackend(setup_runner=setup_runner).prepare(
                regatta=regatta,
                vessel=regatta.vessels[1],
                trial_root=trial_root,
                workspace_path=workspace_path,
                secret_values={"anthropic": "test-secret"},
            )

            self.assertEqual(
                calls[0][0],
                (
                    "nix",
                    "develop",
                    "path:.#pi",
                    "--command",
                    "pi",
                    "install",
                    "npm:@ff-labs/pi-fff",
                ),
            )
            self.assertEqual(calls[0][1]["HOME"], str(instance.temp_home))
            self.assertEqual(calls[0][2], workspace_path)
            self.assertEqual(instance.setup_results[0].stdout, "installed\n")

    def test_prepare_fails_when_rigging_install_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path.mkdir()
            regatta = load_regatta(config_path)

            def setup_runner(
                argv: tuple[str, ...],
                env: dict[str, str],
                cwd: Path,
            ) -> SetupProcessResult:
                return SetupProcessResult(
                    exit_code=1,
                    stdout="",
                    stderr="install failed",
                )

            with self.assertRaisesRegex(
                RuntimePreparationError,
                "failed to install rigging pi-fff target npm:@ff-labs/pi-fff",
            ):
                HostNixRuntimeBackend(setup_runner=setup_runner).prepare(
                    regatta=regatta,
                    vessel=regatta.vessels[1],
                    trial_root=root / "trial",
                    workspace_path=workspace_path,
                    secret_values={"anthropic": "test-secret"},
                )

    def test_prepare_requires_explicit_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            config_path.write_text(PI_WITH_FFF_CONFIG, encoding="utf-8")
            workspace_path.mkdir()
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                RuntimePreparationError,
                "missing value for required secret anthropic",
            ):
                HostNixRuntimeBackend(setup_runner=_passing_setup).prepare(
                    regatta=regatta,
                    vessel=regatta.vessels[0],
                    trial_root=root / "trial",
                    workspace_path=workspace_path,
                    secret_values={},
                )

    def test_prepare_rejects_non_host_nix_runtime_recipe(self) -> None:
        config = PI_WITH_FFF_CONFIG.replace(
            'backend = "host-nix"\nagent = "pi"\nflake = "path:.#pi"',
            (
                'backend = "container"\n'
                'agent = "pi"\n'
                'image = "yacht/pi-agent-runtime:pi-0.74.0"'
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            config_path.write_text(config, encoding="utf-8")
            workspace_path.mkdir()
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                RuntimePreparationError,
                "runtime pi uses unsupported backend container",
            ):
                HostNixRuntimeBackend(setup_runner=_passing_setup).prepare(
                    regatta=regatta,
                    vessel=regatta.vessels[0],
                    trial_root=root / "trial",
                    workspace_path=workspace_path,
                    secret_values={"anthropic": "test-secret"},
                )


class ContainerRuntimeBackendTests(unittest.TestCase):
    def test_prepare_creates_container_runtime_instance_with_explicit_secret(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            trial_root = root / "trial"
            config_path.write_text(CONTAINER_PI_CONFIG, encoding="utf-8")
            workspace_path.mkdir()
            regatta = load_regatta(config_path)

            instance = ContainerRuntimeBackend(setup_runner=_passing_setup).prepare(
                regatta=regatta,
                vessel=regatta.vessels[1],
                trial_root=trial_root,
                workspace_path=workspace_path,
                secret_values={"anthropic": "test-secret"},
            )

            self.assertEqual(instance.runtime.name, "pi-container")
            self.assertEqual(instance.env["HOME"], "/home/yacht")
            self.assertEqual(instance.env["ANTHROPIC_API_KEY"], "test-secret")
            self.assertEqual(
                instance.env["NPM_CONFIG_PREFIX"],
                "/home/yacht/.local/state/npm-global",
            )
            self.assertEqual(
                instance.env["FFF_HISTORY_DB"],
                "/home/yacht/.local/state/fff-history.sqlite",
            )
            self.assertEqual(
                instance.command_prefix,
                (
                    "docker",
                    "run",
                    "--rm",
                    "--workdir",
                    "/workspace",
                    "--env",
                    "HOME=/home/yacht",
                    "--env",
                    "PATH=/home/yacht/.local/state/npm-global/bin:/usr/local/bin:/usr/bin:/bin",
                    "--env",
                    "NPM_CONFIG_CACHE=/home/yacht/.cache/npm",
                    "--env",
                    "NPM_CONFIG_PREFIX=/home/yacht/.local/state/npm-global",
                    "--env",
                    "XDG_CONFIG_HOME=/home/yacht/.config",
                    "--env",
                    "XDG_CACHE_HOME=/home/yacht/.cache",
                    "--env",
                    "XDG_STATE_HOME=/home/yacht/.local/state",
                    "--env",
                    "PI_FFF_MODE=required",
                    "--env",
                    "FFF_FRECENCY_DB=/home/yacht/.local/state/fff-frecency.sqlite",
                    "--env",
                    "FFF_HISTORY_DB=/home/yacht/.local/state/fff-history.sqlite",
                    "--env",
                    "ANTHROPIC_API_KEY",
                    "--mount",
                    f"type=bind,source={workspace_path},target=/workspace",
                    "--mount",
                    f"type=bind,source={instance.temp_home},target=/home/yacht",
                    "yacht/pi-agent-runtime:pi-0.74.0",
                ),
            )
            self.assertTrue(instance.temp_home.is_dir())
            self.assertTrue((instance.temp_home / ".cache" / "npm").is_dir())
            self.assertTrue(
                (instance.temp_home / ".local" / "state" / "npm-global" / "bin")
                .is_dir()
            )
            self.assertEqual(instance.cleanup_paths, (trial_root / "pi-container-fff",))
            self.assertEqual(instance.setup_results[0].target, "npm:@ff-labs/pi-fff")

    def test_prepare_applies_container_rigging_install_inside_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            config_path.write_text(CONTAINER_PI_CONFIG, encoding="utf-8")
            workspace_path.mkdir()
            regatta = load_regatta(config_path)
            calls = []

            def setup_runner(
                argv: tuple[str, ...],
                env: dict[str, str],
                cwd: Path,
            ) -> SetupProcessResult:
                calls.append((argv, env, cwd))
                return SetupProcessResult(
                    exit_code=0,
                    stdout="installed\n",
                    stderr="",
                )

            ContainerRuntimeBackend(setup_runner=setup_runner).prepare(
                regatta=regatta,
                vessel=regatta.vessels[1],
                trial_root=root / "trial",
                workspace_path=workspace_path,
                secret_values={"anthropic": "test-secret"},
            )

            self.assertEqual(calls[0][0][-3:], ("pi", "install", "npm:@ff-labs/pi-fff"))
            self.assertEqual(calls[0][1]["HOME"], "/home/yacht")
            self.assertEqual(calls[0][2], workspace_path)

    def test_prepare_uses_base_container_command_for_rigging_install(self) -> None:
        config = CONTAINER_PI_CONFIG.replace(
            'command = ["pi"]',
            'command = ["pi", "--provider", "anthropic", "--print"]',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            config_path.write_text(config, encoding="utf-8")
            workspace_path.mkdir()
            regatta = load_regatta(config_path)
            calls = []

            def setup_runner(
                argv: tuple[str, ...],
                env: dict[str, str],
                cwd: Path,
            ) -> SetupProcessResult:
                calls.append(argv)
                return SetupProcessResult(
                    exit_code=0,
                    stdout="installed\n",
                    stderr="",
                )

            ContainerRuntimeBackend(setup_runner=setup_runner).prepare(
                regatta=regatta,
                vessel=regatta.vessels[1],
                trial_root=root / "trial",
                workspace_path=workspace_path,
                secret_values={"anthropic": "test-secret"},
            )

            self.assertEqual(calls[0][-3:], ("pi", "install", "npm:@ff-labs/pi-fff"))
            self.assertNotIn("--provider", calls[0])
            self.assertNotIn("--print", calls[0])

    def test_prepare_requires_explicit_container_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            config_path.write_text(CONTAINER_PI_CONFIG, encoding="utf-8")
            workspace_path.mkdir()
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                RuntimePreparationError,
                "missing value for required secret anthropic",
            ):
                ContainerRuntimeBackend(setup_runner=_passing_setup).prepare(
                    regatta=regatta,
                    vessel=regatta.vessels[0],
                    trial_root=root / "trial",
                    workspace_path=workspace_path,
                    secret_values={},
                )


def _passing_setup(
    argv: tuple[str, ...],
    env: dict[str, str],
    cwd: Path,
) -> SetupProcessResult:
    return SetupProcessResult(
        exit_code=0,
        stdout="",
        stderr="",
    )


if __name__ == "__main__":
    unittest.main()
