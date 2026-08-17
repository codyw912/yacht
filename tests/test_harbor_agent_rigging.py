import base64
import importlib.util
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from yacht.runtimes.capabilities import HARBOR_AGENT_EXTENSION_HARNESSES


def _load_rigging_module():
    module_path = (
        Path(__file__).resolve().parent.parent
        / "containers/harbor-launcher/yacht_harbor_agents/rigging.py"
    )
    spec = importlib.util.spec_from_file_location(
        "yacht_harbor_agents_rigging", module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rigging = _load_rigging_module()


class HarborAgentRiggingTests(unittest.TestCase):
    def test_package_step_installs_pinned_npm_target(self) -> None:
        commands = rigging.rigging_commands(
            [{"method": "package", "target": "npm:@ff-labs/mcp-fff@0.3.0"}]
        )
        self.assertEqual(commands, ["npm install -g @ff-labs/mcp-fff@0.3.0"])

    def test_package_step_requires_npm_prefix(self) -> None:
        with self.assertRaisesRegex(ValueError, "npm: prefix"):
            rigging.rigging_commands(
                [{"method": "package", "target": "pip:some-package==1.0"}]
            )

    def test_config_file_step_writes_content_into_home(self) -> None:
        content = '{"mode": "fast"}\nline two\'s "quotes" $HOME `backticks`\n'
        commands = rigging.rigging_commands(
            [
                {
                    "method": "config-file",
                    "target": "fff/config.json",
                    "content": content,
                }
            ]
        )
        self.assertEqual(len(commands), 1)
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        self.assertIn(encoded, commands[0])

        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                ["sh", "-c", commands[0]],
                env={"HOME": temp_dir, "PATH": "/usr/bin:/bin"},
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            written = Path(temp_dir, "fff/config.json").read_text(encoding="utf-8")
            self.assertEqual(written, content)

    def test_config_file_step_rejects_escaping_paths(self) -> None:
        for target in ("/etc/passwd", "../outside", "a/../../b"):
            with self.assertRaisesRegex(ValueError, "relative path"):
                rigging.rigging_commands(
                    [
                        {
                            "method": "config-file",
                            "target": target,
                            "content": "x",
                        }
                    ]
                )

    def test_rejects_unsupported_methods(self) -> None:
        with self.assertRaisesRegex(ValueError, "not supported"):
            rigging.rigging_commands([{"method": "mcp-server", "target": "fff"}])

    def test_agent_extension_step_installs_through_pi(self) -> None:
        commands = rigging.rigging_commands(
            [
                {
                    "method": "agent-extension",
                    "target": "npm:pi-mcp-adapter@2.15.0",
                    "agent": "pi",
                }
            ]
        )

        self.assertEqual(len(commands), 1)
        self.assertIn(". ~/.nvm/nvm.sh; pi install", commands[0])
        self.assertIn("npm:pi-mcp-adapter@2.15.0", commands[0])

    def test_agent_extension_step_rejects_unknown_agents(self) -> None:
        with self.assertRaises(ValueError):
            rigging.rigging_commands(
                [
                    {
                        "method": "agent-extension",
                        "target": "npm:x@1.0.0",
                        "agent": "claude-code",
                    }
                ]
            )

    def test_pi_package_names_the_current_scope(self) -> None:
        # pi's npm home moved from @mariozechner to @earendil-works at
        # 0.74.0; harbor 0.20.0 still installs the retired scope, whose
        # last release predates every current pi extension build.
        # YachtPi's install override must name the current package.
        self.assertEqual(rigging.PI_PACKAGE, "@earendil-works/pi-coding-agent")

    def test_node_alias_repair_reaims_default_at_the_installed_node(self) -> None:
        # Official node base images set NODE_VERSION; nvm's installer
        # pre-installs that version and pins the default alias to it, so
        # fresh exec sessions miss the node harbor installed (and every
        # npm -g binary in it, pi included). The repair command must
        # re-source nvm and re-aim default at the latest installed node.
        command = rigging.PI_NODE_ALIAS_REPAIR_COMMAND
        self.assertIn(". ~/.nvm/nvm.sh", command)
        self.assertIn("nvm alias default node", command)

    def test_agent_extension_installers_match_the_harbor_capability_gate(
        self,
    ) -> None:
        # The launcher's installer map and yacht's capability gate
        # (HARBOR_AGENT_EXTENSION_HARNESSES) must name the same agents:
        # a harness the gate lets through but the launcher can't install
        # for would fail mid-trial, after tokens are spent.
        self.assertEqual(
            set(rigging._AGENT_EXTENSION_INSTALLERS),
            HARBOR_AGENT_EXTENSION_HARNESSES,
        )

    def test_omp_and_codex_run_commands_quote_and_pin_native_flags(self) -> None:
        import shlex

        omp = rigging.omp_run_command(
            instruction="solve 'it'",
            model="openai/gpt-5.2",
        )
        self.assertIn("omp -p --mode json --no-session --auto-approve", omp)
        self.assertIn("--model openai/gpt-5.2", omp)
        self.assertIn(shlex.quote("solve 'it'"), omp)
        self.assertIn("> /logs/agent/omp.jsonl", omp)

        codex = rigging.codex_run_command(
            instruction="solve 'it'",
            model="openai/gpt-5.2",
        )
        self.assertIn("codex exec --json --ephemeral", codex)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", codex)
        self.assertIn("--model openai/gpt-5.2", codex)
        self.assertIn(shlex.quote("solve 'it'"), codex)
        self.assertIn("> /logs/agent/codex.jsonl", codex)

    def test_codex_run_command_writes_auth_json_from_env(self) -> None:
        setup = rigging.codex_auth_setup_command()
        self.assertIn("CODEX_HOME=/tmp/codex-home", setup)
        self.assertIn("process.env.OPENAI_API_KEY", setup)
        self.assertNotIn("sk-", setup)

        command = rigging.codex_run_command(
            instruction="solve it",
            model="openai/gpt-5.6-luna",
        )
        self.assertLess(command.index(setup), command.index("codex exec"))

        dummy = "sk-dummy-yacht-codex-auth"
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "codex-home"
            secrets = Path(temp_dir) / "codex-secrets"
            rewritten = setup.replace("/tmp/codex-home", str(home)).replace(
                "/tmp/codex-secrets", str(secrets)
            )
            env = os.environ.copy()
            env["OPENAI_API_KEY"] = dummy
            completed = subprocess.run(
                ["bash", "-lc", rewritten],
                check=True,
                env=env,
                capture_output=True,
                text=True,
            )
            auth = home / "auth.json"
            payload = json.loads(auth.read_text(encoding="utf-8"))
            self.assertTrue(auth.is_symlink())
            self.assertEqual(payload, {"OPENAI_API_KEY": dummy})
            self.assertEqual(stat.S_IMODE(auth.stat().st_mode), 0o600)
            self.assertEqual(completed.stdout, "")

    def test_version_contains_pin_reads_cli_banner(self) -> None:
        self.assertTrue(rigging.version_contains_pin("omp/17.2.15", "17.2.15"))
        self.assertTrue(rigging.version_contains_pin("codex-cli 0.147.0", "0.147.0"))
        self.assertFalse(rigging.version_contains_pin("omp/17.2.15", "9.9.9"))

    def test_omp_install_installs_bun_before_omp(self) -> None:
        command = rigging.omp_install_command("@17.2.15")
        self.assertIn("npm install -g bun@1.3.14", command)
        self.assertIn("npm install -g @oh-my-pi/pi-coding-agent@17.2.15", command)
        bun_at = command.index("bun@1.3.14")
        omp_at = command.index("@oh-my-pi/pi-coding-agent@17.2.15")
        self.assertLess(bun_at, omp_at)


if __name__ == "__main__":
    unittest.main()
