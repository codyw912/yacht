import os
import unittest

from yacht.runtime_process import subprocess_env


class RuntimeProcessTests(unittest.TestCase):
    def test_docker_process_env_preserves_host_path_and_runtime_secrets(self) -> None:
        runtime_env = {
            "PATH": "/home/yacht/.local/state/npm-global/bin:/usr/local/bin:/usr/bin:/bin",
            "HOME": "/home/yacht",
            "ANTHROPIC_API_KEY": "test-secret",
        }

        env = subprocess_env(("docker", "run", "image", "pi", "--version"), runtime_env)

        self.assertEqual(env["PATH"], os.environ["PATH"])
        self.assertEqual(env["HOME"], "/home/yacht")
        self.assertEqual(env["ANTHROPIC_API_KEY"], "test-secret")

    def test_non_docker_process_env_uses_runtime_path(self) -> None:
        runtime_env = {"PATH": "/tmp/runtime-bin", "HOME": "/tmp/home"}

        env = subprocess_env(("nix", "develop", "path:.#pi"), runtime_env)

        self.assertEqual(env["PATH"], "/tmp/runtime-bin")
        self.assertEqual(env["HOME"], "/tmp/home")
