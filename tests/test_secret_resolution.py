"""Secret resolution, ambient-environment hardening, and redaction.

Every test here uses an unmistakable dummy sentinel. Nothing in this
module reads a real credential or contacts a secret provider.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from yacht.cli import main
from yacht.config.loader import load_regatta
from yacht.domain.model import ConfigError
from yacht.preflight import CommandResult
from yacht.runtimes.container import resolve_container_runtime
from yacht.runtimes.host_nix import resolve_host_nix_runtime
from yacht.runtimes.process import subprocess_env
from yacht.runtimes.secrets import secret_env_by_vessel
from yacht.secret_resolution import ResolvedSecrets, resolve_secret_arguments

SENTINEL = "yacht-dummy-sentinel-DO-NOT-USE-4f7ba2"
OTHER_SENTINEL = "yacht-dummy-sentinel-DO-NOT-USE-a1c908"

HOST_NIX_CONFIG = """
[regatta]
name = "secret-hardening"

[course]
name = "tiny-course"
tasks = [
  { id = "task-1", title = "Fix a failing test", difficulty = 1 },
]

[secrets.anthropic]
source = "env"
name = "ANTHROPIC_API_KEY"

[runtimes.declaring]
backend = "host-nix"
flake = "github:example/yacht-runtimes#mock"
command = ["mock-agent"]
required_secrets = ["anthropic"]

[runtimes.declaring.preflight]
required = true
checks = [
  { name = "runtime-home-isolated", kind = "path-isolation", env = ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"] },
]

[runtimes.plain]
backend = "host-nix"
flake = "github:example/yacht-runtimes#mock"
command = ["mock-agent"]

[runtimes.plain.preflight]
required = true
checks = [
  { name = "runtime-home-isolated", kind = "path-isolation", env = ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"] },
]

[[vessels]]
name = "with-secret"
model = "mock"
runtime = "declaring"

[[vessels]]
name = "without-secret"
model = "mock"
runtime = "plain"

[[comparisons]]
name = "secret-vs-none"
course = "tiny-course"
vessels = ["with-secret", "without-secret"]
"""

CONTAINER_CONFIG = """
[regatta]
name = "secret-hardening-container"

[course]
name = "tiny-course"
tasks = [
  { id = "task-1", title = "Fix a failing test", difficulty = 1 },
]

[secrets.anthropic]
source = "env"
name = "ANTHROPIC_API_KEY"

[runtimes.container-agent]
backend = "container"
image = "yacht/pi-agent-runtime:pi-0.74.0"
command = ["pi"]
container_home = "/home/yacht"
container_workspace = "/workspace"
required_secrets = ["anthropic"]

[runtimes.container-agent.preflight]
required = true
checks = [
  { name = "runtime-home-isolated", kind = "path-isolation", env = ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"] },
]

[[vessels]]
name = "container-vessel"
model = "mock"
runtime = "container-agent"

[[vessels]]
name = "container-vessel-b"
model = "mock"
runtime = "container-agent"

[[comparisons]]
name = "container-only"
course = "tiny-course"
vessels = ["container-vessel", "container-vessel-b"]
"""


class SecretArgumentResolutionTests(unittest.TestCase):
    def test_resolves_env_reference_and_scrubs_only_that_variable(self) -> None:
        environ = {
            "ANTHROPIC_API_KEY": SENTINEL,
            "PATH": "/usr/bin",
            "ANTHROPIC_API_KEY_BACKUP": OTHER_SENTINEL,
        }

        resolved = resolve_secret_arguments(
            ["anthropic=@env:ANTHROPIC_API_KEY"],
            environ=environ,
        )

        self.assertEqual(dict(resolved), {"anthropic": SENTINEL})
        self.assertEqual(resolved.blocked_env_names, frozenset({"ANTHROPIC_API_KEY"}))
        # Only the exact referenced name leaves the environment: no
        # prefix or pattern matching.
        self.assertEqual(
            environ,
            {"PATH": "/usr/bin", "ANTHROPIC_API_KEY_BACKUP": OTHER_SENTINEL},
        )

    def test_literal_secret_touches_no_environment_variable(self) -> None:
        environ = {"ANTHROPIC_API_KEY": SENTINEL}

        resolved = resolve_secret_arguments(["anthropic=literal"], environ=environ)

        self.assertEqual(dict(resolved), {"anthropic": "literal"})
        self.assertEqual(resolved.blocked_env_names, frozenset())
        self.assertEqual(environ, {"ANTHROPIC_API_KEY": SENTINEL})

    def test_two_logical_names_may_reference_one_source_variable(self) -> None:
        environ = {"ANTHROPIC_API_KEY": SENTINEL}

        resolved = resolve_secret_arguments(
            [
                "anthropic=@env:ANTHROPIC_API_KEY",
                "anthropic_rigging=@env:ANTHROPIC_API_KEY",
            ],
            environ=environ,
        )

        self.assertEqual(
            dict(resolved),
            {"anthropic": SENTINEL, "anthropic_rigging": SENTINEL},
        )
        self.assertEqual(resolved.blocked_env_names, frozenset({"ANTHROPIC_API_KEY"}))
        self.assertEqual(environ, {})

    def test_repeated_logical_name_scrubs_every_referenced_variable(self) -> None:
        # The scoped wrappers append their own --secret after the caller's
        # arguments, so a logical name can arrive twice. The last entry
        # wins for the value; the overridden variable must not be left
        # behind in the ambient environment.
        environ = {
            "OPERATOR_KEY": OTHER_SENTINEL,
            "ANTHROPIC_API_KEY": SENTINEL,
            "PATH": "/usr/bin",
        }

        resolved = resolve_secret_arguments(
            [
                "anthropic=@env:OPERATOR_KEY",
                "anthropic=@env:ANTHROPIC_API_KEY",
            ],
            environ=environ,
        )

        self.assertEqual(dict(resolved), {"anthropic": SENTINEL})
        self.assertEqual(
            resolved.blocked_env_names,
            frozenset({"OPERATOR_KEY", "ANTHROPIC_API_KEY"}),
        )
        self.assertEqual(environ, {"PATH": "/usr/bin"})

    def test_literal_override_still_scrubs_the_overridden_reference(self) -> None:
        environ = {"OPERATOR_KEY": OTHER_SENTINEL, "PATH": "/usr/bin"}

        resolved = resolve_secret_arguments(
            ["anthropic=@env:OPERATOR_KEY", "anthropic=literal"],
            environ=environ,
        )

        self.assertEqual(dict(resolved), {"anthropic": "literal"})
        self.assertEqual(resolved.blocked_env_names, frozenset({"OPERATOR_KEY"}))
        self.assertEqual(environ, {"PATH": "/usr/bin"})

    def test_parse_failure_leaves_the_environment_unchanged(self) -> None:
        cases = [
            (["anthropic=@env:ANTHROPIC_API_KEY", "missing-equals"], "NAME=VALUE"),
            (["anthropic=@env:ANTHROPIC_API_KEY", "=value"], "non-empty"),
            (["anthropic=@env:ANTHROPIC_API_KEY", "openai="], "must be non-empty"),
            (["anthropic=@env:ANTHROPIC_API_KEY", "openai=@env:"], "must name an env"),
            (
                ["anthropic=@env:ANTHROPIC_API_KEY", "openai=@env:YACHT_MISSING_KEY"],
                "YACHT_MISSING_KEY is not set",
            ),
            (
                ["anthropic=@env:ANTHROPIC_API_KEY", "empty=@env:YACHT_EMPTY_KEY"],
                "YACHT_EMPTY_KEY is empty",
            ),
        ]
        for values, message in cases:
            with self.subTest(values=values):
                environ = {
                    "ANTHROPIC_API_KEY": SENTINEL,
                    "YACHT_EMPTY_KEY": "",
                    "PATH": "/usr/bin",
                }
                before = dict(environ)

                with self.assertRaisesRegex(ConfigError, message):
                    resolve_secret_arguments(values, environ=environ)

                self.assertEqual(environ, before)

    def test_repr_never_renders_a_value(self) -> None:
        resolved = ResolvedSecrets(
            values={"anthropic": SENTINEL},
            blocked_env_names=frozenset({"ANTHROPIC_API_KEY"}),
        )

        rendered = repr(resolved)

        self.assertNotIn(SENTINEL, rendered)
        self.assertIn("anthropic", rendered)
        self.assertIn("ANTHROPIC_API_KEY", rendered)

    def test_unrelated_helper_subprocess_cannot_inherit_the_source_variable(
        self,
    ) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": SENTINEL}):
            resolved = resolve_secret_arguments(["anthropic=@env:ANTHROPIC_API_KEY"])
            self.assertEqual(resolved["anthropic"], SENTINEL)
            self.assertNotIn("ANTHROPIC_API_KEY", os.environ)

            # A helper that declared nothing: git, a dataset download, a
            # rigging install for a vessel with no secrets.
            argv = (
                sys.executable,
                "-c",
                "import json, os; print(json.dumps(dict(os.environ)))",
            )
            completed = subprocess.run(
                argv,
                env=subprocess_env(argv, {}),
                capture_output=True,
                text=True,
                check=True,
            )

            self.assertNotIn(SENTINEL, completed.stdout)
            self.assertNotIn("ANTHROPIC_API_KEY", json.loads(completed.stdout))


class RuntimeSecretInjectionTests(unittest.TestCase):
    def test_declaring_runtime_receives_the_value_and_others_do_not(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta = _load_config(root, HOST_NIX_CONFIG)
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": SENTINEL}):
                resolved = resolve_secret_arguments(
                    ["anthropic=@env:ANTHROPIC_API_KEY"]
                )

                declaring = _host_nix_env(regatta, "with-secret", root, resolved)
                plain = _host_nix_env(regatta, "without-secret", root, resolved)

                self.assertEqual(declaring["ANTHROPIC_API_KEY"], SENTINEL)
                self.assertNotIn("ANTHROPIC_API_KEY", plain)

                argv = ("mock-agent",)
                self.assertEqual(
                    subprocess_env(argv, declaring)["ANTHROPIC_API_KEY"],
                    SENTINEL,
                )
                self.assertNotIn("ANTHROPIC_API_KEY", subprocess_env(argv, plain))

    def test_container_command_construction_stays_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta = _load_config(root, CONTAINER_CONFIG)
            vessel = _vessel(regatta, "container-vessel")
            resolution = resolve_container_runtime(
                regatta=regatta,
                vessel=vessel,
                instance_root=root / "instance",
                workspace_path=root / "workspace",
            )

            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": SENTINEL}):
                resolved = resolve_secret_arguments(
                    ["anthropic=@env:ANTHROPIC_API_KEY"]
                )
                env = resolution.env_with_secret_values(
                    regatta=regatta,
                    secret_values=resolved,
                )

            prefix = list(resolution.command_prefix)
            # The secret crosses the container boundary by name only.
            self.assertIn("ANTHROPIC_API_KEY", prefix)
            self.assertEqual(
                prefix[prefix.index("ANTHROPIC_API_KEY") - 1],
                "--env",
            )
            self.assertNotIn(SENTINEL, " ".join(prefix))
            self.assertEqual(env["ANTHROPIC_API_KEY"], SENTINEL)
            # docker inherits the value from the env Yacht hands it.
            self.assertEqual(
                subprocess_env(tuple(prefix), env)["ANTHROPIC_API_KEY"],
                SENTINEL,
            )

    def test_native_launcher_env_is_scoped_to_declaring_vessels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            regatta = _load_config(root, HOST_NIX_CONFIG)

            per_vessel = secret_env_by_vessel(regatta, {"anthropic": SENTINEL})

            self.assertEqual(
                per_vessel,
                {"with-secret": {"ANTHROPIC_API_KEY": SENTINEL}},
            )


class SecretRedactionTests(unittest.TestCase):
    def test_preflight_artifacts_carry_redacted_references_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            config_path.write_text(HOST_NIX_CONFIG, encoding="utf-8")
            logbook_dir = root / "logbook"
            workspace_dir = root / "workspace"
            workspace_dir.mkdir()

            stdout = StringIO()
            stderr = StringIO()
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": SENTINEL}):
                with patch(
                    "yacht.preflight._run_command",
                    return_value=CommandResult(exit_code=0, stdout="ok\n", stderr=""),
                ):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = main(
                            [
                                "internals",
                                "preflight",
                                str(config_path),
                                "--logbook",
                                str(logbook_dir),
                                "--workspace",
                                str(workspace_dir),
                                "--secret",
                                "anthropic=@env:ANTHROPIC_API_KEY",
                            ]
                        )

            self.assertEqual(exit_code, 0, stderr.getvalue())
            self.assertNotIn(SENTINEL, stdout.getvalue())
            self.assertNotIn(SENTINEL, stderr.getvalue())

            artifact = json.loads(
                (
                    logbook_dir / "preflight" / "secret-vs-none" / "with-secret.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                artifact["secret_refs"],
                [
                    {
                        "name": "anthropic",
                        "source": "env",
                        "ref": "ANTHROPIC_API_KEY",
                        "redacted": True,
                    }
                ],
            )

            written = sorted(path for path in logbook_dir.rglob("*") if path.is_file())
            self.assertTrue(written)
            for path in written:
                with self.subTest(artifact=str(path)):
                    self.assertNotIn(
                        SENTINEL,
                        path.read_text(encoding="utf-8", errors="replace"),
                    )


def _load_config(root: Path, config: str):
    config_path = root / "regatta.toml"
    config_path.write_text(config, encoding="utf-8")
    return load_regatta(config_path)


def _vessel(regatta, name: str):
    for vessel in regatta.vessels:
        if vessel.name == name:
            return vessel
    raise AssertionError(f"missing vessel {name}")


def _host_nix_env(regatta, vessel_name: str, root: Path, resolved) -> dict[str, str]:
    resolution = resolve_host_nix_runtime(
        regatta=regatta,
        vessel=_vessel(regatta, vessel_name),
        instance_root=root / "instance" / vessel_name,
        workspace_path=root / "workspace",
    )
    return resolution.env_with_secret_values(
        regatta=regatta,
        secret_values=resolved,
    )


if __name__ == "__main__":
    unittest.main()
