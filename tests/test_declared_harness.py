import json
import stat
import tempfile
import unittest
from pathlib import Path

from yacht.contracts.schemas import (
    BUILT_IN_HARNESS_NAMES,
    SchemaValidationError,
    validate_harness_evidence_document,
)
from yacht.domain.model import (
    ConfigError,
    HarnessDeclaration,
    RuntimeInstance,
    RuntimeRecipe,
    Task,
    load_regatta,
)
from yacht.harnesses.declared import (
    DeclaredHarnessAdapter,
    DeclaredHarnessEvidenceError,
)
from yacht.harnesses.registry import (
    supported_harness_names,
    task_agent,
)


VALID_EVIDENCE = {
    "schema": "yacht.harness-evidence.v1",
    "response": "done",
    "usage": {"input_tokens": 120, "output_tokens": 30},
    "tool_calls": [{"name": "read_file", "count": 2}],
    "cost": {"total_usd": 0.004},
    "model": "test-model-1",
    "extras": {"session_id": "abc"},
}


DECLARED_CONFIG = """
[regatta]
name = "declared-harness-smoke"

[course]
name = "swe-bench-lite"

[[course.tasks]]
id = "task-1"
title = "A task"

[course.adapter]
kind = "swe-bench"
dataset = "princeton-nlp/SWE-bench_Lite"
split = "test"
harness = "docker"

[harnesses.yach]
prompt = "stdin"
evidence = "file"

[runtimes.yach-host]
backend = "host-nix"
flake = "path:."
command = ["yach", "run"]
harness = "yach"

[[vessels]]
name = "yach-baseline"
model = "claude-haiku-4-5"
runtime = "yach-host"

[[vessels]]
name = "yach-candidate"
model = "claude-haiku-4-5"
runtime = "yach-host"

[[comparisons]]
name = "baseline-vs-candidate"
course = "swe-bench-lite"
vessels = ["yach-baseline", "yach-candidate"]
"""


def _write_harness_script(root: Path, body: str) -> Path:
    script = root / "fake-harness.sh"
    script.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _instance(root: Path, script: Path) -> RuntimeInstance:
    runtime = RuntimeRecipe(
        name="declared-host",
        backend="host-nix",
        command=(str(script),),
        harness="fake",
    )
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return RuntimeInstance(
        runtime=runtime,
        temp_home=root / "home",
        workspace_path=workspace,
        env={"HOME": str(root / "home"), "PATH": "/usr/bin:/bin"},
        command_prefix=(),
        cleanup_paths=(),
    )


def _task() -> Task:
    return Task(id="task-1", title="A task", difficulty=1)


class HarnessDeclarationConfigTests(unittest.TestCase):
    def test_parses_declaration_with_explicit_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(DECLARED_CONFIG, encoding="utf-8")

            regatta = load_regatta(config_path)

        declaration = regatta.harness_declarations["yach"]
        self.assertEqual(declaration.name, "yach")
        self.assertEqual(declaration.prompt, "stdin")
        self.assertEqual(declaration.evidence, "file")

    def test_declaration_defaults_to_argument_and_stdout(self) -> None:
        config = DECLARED_CONFIG.replace(
            '[harnesses.yach]\nprompt = "stdin"\nevidence = "file"\n',
            "[harnesses.yach]\n",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            regatta = load_regatta(config_path)

        declaration = regatta.harness_declarations["yach"]
        self.assertEqual(declaration.prompt, "argument")
        self.assertEqual(declaration.evidence, "stdout")

    def test_rejects_shadowing_a_built_in_harness(self) -> None:
        config = DECLARED_CONFIG.replace("[harnesses.yach]", "[harnesses.pi]")
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError, "must not shadow the built-in harness pi"
            ):
                load_regatta(config_path)

    def test_rejects_unknown_prompt_mode(self) -> None:
        config = DECLARED_CONFIG.replace('prompt = "stdin"', 'prompt = "socket"')
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError, "harnesses.yach.prompt must be one of"
            ):
                load_regatta(config_path)

    def test_built_in_names_constant_matches_the_registry(self) -> None:
        self.assertEqual(BUILT_IN_HARNESS_NAMES, set(supported_harness_names()))


class HarnessEvidenceSchemaTests(unittest.TestCase):
    def test_accepts_a_full_evidence_document(self) -> None:
        validate_harness_evidence_document(VALID_EVIDENCE)

    def test_accepts_minimal_evidence(self) -> None:
        validate_harness_evidence_document(
            {
                "schema": "yacht.harness-evidence.v1",
                "response": "",
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        )

    def test_rejects_wrong_schema(self) -> None:
        with self.assertRaisesRegex(SchemaValidationError, "schema must be"):
            validate_harness_evidence_document({**VALID_EVIDENCE, "schema": "v2"})

    def test_rejects_missing_usage(self) -> None:
        evidence = {k: v for k, v in VALID_EVIDENCE.items() if k != "usage"}
        with self.assertRaisesRegex(SchemaValidationError, "usage"):
            validate_harness_evidence_document(evidence)

    def test_rejects_boolean_token_counts(self) -> None:
        evidence = {
            **VALID_EVIDENCE,
            "usage": {"input_tokens": True, "output_tokens": 1},
        }
        with self.assertRaisesRegex(SchemaValidationError, "input_tokens"):
            validate_harness_evidence_document(evidence)

    def test_rejects_tool_calls_without_counts(self) -> None:
        evidence = {**VALID_EVIDENCE, "tool_calls": [{"name": "read_file"}]}
        with self.assertRaisesRegex(SchemaValidationError, "count"):
            validate_harness_evidence_document(evidence)


class DeclaredHarnessAdapterTests(unittest.TestCase):
    def test_argument_prompt_with_stdout_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = _write_harness_script(
                root,
                f"echo \"working log line\"\necho '{json.dumps(VALID_EVIDENCE)}'\n",
            )
            adapter = DeclaredHarnessAdapter(HarnessDeclaration(name="fake"))

            result = adapter.run_task(
                instance=_instance(root, script),
                task=_task(),
                prompt="do the thing",
                env={"PATH": "/usr/bin:/bin"},
                cwd=root / "workspace",
                transcript_path=root / "transcripts" / "task-1.json",
            )

            transcript = json.loads(result.transcript_path.read_text(encoding="utf-8"))

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.response, "done")
        self.assertEqual(result.tool_calls, ("read_file",))
        self.assertEqual(result.metrics.tokens, 150)
        self.assertEqual(result.metrics.usage_source, "reported")
        self.assertEqual(result.machine_evidence["format"], "yacht-harness-evidence")
        self.assertEqual(transcript["task_id"], "task-1")
        self.assertIn("do the thing", transcript["argv"])

    def test_stdin_prompt_reaches_the_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = dict(VALID_EVIDENCE)
            script = _write_harness_script(
                root,
                "read -r prompt_line\n"
                'echo "{\\"schema\\": \\"yacht.harness-evidence.v1\\", '
                '\\"response\\": \\"got: $prompt_line\\", '
                '\\"usage\\": {\\"input_tokens\\": 1, \\"output_tokens\\": 1}}"\n',
            )
            del evidence
            adapter = DeclaredHarnessAdapter(
                HarnessDeclaration(name="fake", prompt="stdin")
            )

            result = adapter.run_task(
                instance=_instance(root, script),
                task=_task(),
                prompt="hello from stdin",
                env={"PATH": "/usr/bin:/bin"},
                cwd=root / "workspace",
                transcript_path=root / "transcripts" / "task-1.json",
            )

            transcript = json.loads(result.transcript_path.read_text(encoding="utf-8"))

        self.assertEqual(result.response, "got: hello from stdin")
        self.assertNotIn("hello from stdin", transcript["argv"])

    def test_file_evidence_via_environment_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = _write_harness_script(
                root,
                'echo "noisy stdout without json"\n'
                f"echo '{json.dumps(VALID_EVIDENCE)}' > \"$YACHT_EVIDENCE_PATH\"\n",
            )
            adapter = DeclaredHarnessAdapter(
                HarnessDeclaration(name="fake", evidence="file")
            )

            result = adapter.run_task(
                instance=_instance(root, script),
                task=_task(),
                prompt="do the thing",
                env={"PATH": "/usr/bin:/bin"},
                cwd=root / "workspace",
                transcript_path=root / "transcripts" / "task-1.json",
            )

        self.assertEqual(result.response, "done")
        self.assertEqual(result.metrics.tokens, 150)

    def test_exit_zero_without_evidence_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = _write_harness_script(root, 'echo "no evidence here"\n')
            adapter = DeclaredHarnessAdapter(HarnessDeclaration(name="fake"))

            with self.assertRaises(DeclaredHarnessEvidenceError):
                adapter.run_task(
                    instance=_instance(root, script),
                    task=_task(),
                    prompt="do the thing",
                    env={"PATH": "/usr/bin:/bin"},
                    cwd=root / "workspace",
                    transcript_path=root / "transcripts" / "task-1.json",
                )

    def test_nonzero_exit_records_a_failed_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = _write_harness_script(root, 'echo "crash" >&2\nexit 3\n')
            adapter = DeclaredHarnessAdapter(HarnessDeclaration(name="fake"))

            result = adapter.run_task(
                instance=_instance(root, script),
                task=_task(),
                prompt="do the thing",
                env={"PATH": "/usr/bin:/bin"},
                cwd=root / "workspace",
                transcript_path=root / "transcripts" / "task-1.json",
            )

        self.assertEqual(result.exit_code, 3)
        self.assertEqual(result.metrics.tokens, 0)
        self.assertIsNone(result.metrics.usage_source)
        self.assertEqual(result.machine_evidence, {})


class DeclaredHarnessRegistryTests(unittest.TestCase):
    def test_resolves_declared_harness_through_the_registry(self) -> None:
        declaration = HarnessDeclaration(name="yach")
        agent = task_agent("yach", {"yach": declaration})
        self.assertIsInstance(agent, DeclaredHarnessAdapter)

    def test_unknown_harness_without_declarations_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "unsupported task attempt agent yach"):
            task_agent("yach")

    def test_built_ins_resolve_without_declarations(self) -> None:
        self.assertIsNotNone(task_agent("pi"))


if __name__ == "__main__":
    unittest.main()
