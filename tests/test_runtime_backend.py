import tempfile
import unittest
from pathlib import Path

from tests.test_provisioning import PI_WITH_FFF_CONFIG
from yacht.regatta import load_regatta
from yacht.runtime_backend import HostNixRuntimeBackend, RuntimePreparationError


class HostNixRuntimeBackendTests(unittest.TestCase):
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

            instance = HostNixRuntimeBackend().prepare(
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
                ("nix", "develop", "github:example/yacht-runtimes#pi", "--command"),
            )
            self.assertEqual(instance.env["ANTHROPIC_API_KEY"], "test-secret")
            self.assertEqual(instance.env["HOME"], str(instance.temp_home))
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
            self.assertTrue((instance.temp_home / ".local" / "state").is_dir())
            self.assertEqual(instance.cleanup_paths, (trial_root / "pi-plus-fff",))

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
                HostNixRuntimeBackend().prepare(
                    regatta=regatta,
                    vessel=regatta.vessels[0],
                    trial_root=root / "trial",
                    workspace_path=workspace_path,
                    secret_values={},
                )

    def test_prepare_rejects_non_host_nix_runtime_recipe(self) -> None:
        config = PI_WITH_FFF_CONFIG.replace('backend = "host-nix"', 'backend = "docker"')
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            workspace_path = root / "workspace"
            config_path.write_text(config, encoding="utf-8")
            workspace_path.mkdir()
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(
                RuntimePreparationError,
                "runtime pi uses unsupported backend docker",
            ):
                HostNixRuntimeBackend().prepare(
                    regatta=regatta,
                    vessel=regatta.vessels[0],
                    trial_root=root / "trial",
                    workspace_path=workspace_path,
                    secret_values={"anthropic": "test-secret"},
                )


if __name__ == "__main__":
    unittest.main()
