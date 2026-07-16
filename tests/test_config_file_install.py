import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import ConfigError, load_regatta


def _config(install_line: str) -> str:
    return f"""
[regatta]
name = "config-file-install"

[course]
name = "tiny-course"
tasks = [
  {{ id = "task-1", title = "Fix a failing test", difficulty = 1 }},
]

[runtimes.box]
backend = "container"
harness = "pi"
image = "yacht/test-image:1"
command = ["pi"]

[riggings.tool]
tools = []

[[riggings.tool.install]]
{install_line}

[[vessels]]
name = "baseline"
model = "mock"
runtime = "box"
"""


class ConfigFileInstallTests(unittest.TestCase):
    def test_inline_content_parses(self) -> None:
        regatta = self._load(
            'method = "config-file"\n'
            'target = ".config/tool/settings.json"\n'
            "content = '{\"enabled\": true}'"
        )

        step = regatta.rigging_recipes["tool"].install[0]
        self.assertEqual(step.method, "config-file")
        self.assertEqual(step.content, '{"enabled": true}')

    def test_source_reads_file_relative_to_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "settings.json").write_text('{"from": "file"}', encoding="utf-8")
            config_path = root / "regatta.toml"
            config_path.write_text(
                _config(
                    'method = "config-file"\n'
                    'target = ".config/tool/settings.json"\n'
                    'source = "settings.json"'
                ),
                encoding="utf-8",
            )

            regatta = load_regatta(config_path)

            step = regatta.rigging_recipes["tool"].install[0]
            self.assertEqual(step.content, '{"from": "file"}')

    def test_rejects_content_and_source_together(self) -> None:
        with self.assertRaisesRegex(
            ConfigError, "must not define both content and source"
        ):
            self._load(
                'method = "config-file"\n'
                'target = ".config/x"\n'
                'content = "{}"\n'
                'source = "x.json"'
            )

    def test_requires_content_or_source(self) -> None:
        with self.assertRaisesRegex(ConfigError, "requires content or source"):
            self._load('method = "config-file"\ntarget = ".config/x"')

    def test_reports_missing_source_file(self) -> None:
        with self.assertRaisesRegex(ConfigError, "source not found"):
            self._load(
                'method = "config-file"\ntarget = ".config/x"\nsource = "missing.json"'
            )

    def _load(self, install_line: str):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(_config(install_line), encoding="utf-8")
            return load_regatta(config_path)


if __name__ == "__main__":
    unittest.main()
