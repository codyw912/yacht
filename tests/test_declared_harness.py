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


def _load_declared_support():
    import importlib.util

    module_path = (
        Path(__file__).resolve().parent.parent
        / "containers/harbor-launcher/yacht_harbor_agents/declared_support.py"
    )
    spec = importlib.util.spec_from_file_location(
        "yacht_harbor_agents_declared_support", module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


declared_support = _load_declared_support()

HARBOR_DECLARATION = {
    "name": "yach",
    "prompt": "argument",
    "evidence": "file",
    "command": ["yach", "run", "--model", "{model}"],
    "install": {"path": "/tmp/dist/yach", "sha256": "a" * 64},
}


class DeclaredSupportTests(unittest.TestCase):
    def test_verify_artifact_accepts_matching_digest(self) -> None:
        import hashlib

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "yach"
            artifact.write_bytes(b"binary-bytes")
            digest = hashlib.sha256(b"binary-bytes").hexdigest()

            declared_support.verify_artifact(artifact, digest)

    def test_verify_artifact_rejects_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "yach"
            artifact.write_bytes(b"binary-bytes")

            with self.assertRaisesRegex(Exception, "does not match"):
                declared_support.verify_artifact(artifact, "b" * 64)

    def test_run_command_substitutes_model_and_maps_binary(self) -> None:
        command = declared_support.run_command(
            HARBOR_DECLARATION,
            model="claude-haiku-4-5",
            instruction="solve it",
        )

        self.assertIn("/installed-agent/bin/yach run --model claude-haiku-4-5", command)
        self.assertIn("'solve it'", command)
        self.assertIn("YACHT_EVIDENCE_PATH=/logs/agent/harness-evidence.json", command)

    def test_run_command_stdin_pipes_the_instruction(self) -> None:
        declaration = {**HARBOR_DECLARATION, "prompt": "stdin"}

        command = declared_support.run_command(
            declaration, model="m", instruction="solve it"
        )

        self.assertIn("printf %s 'solve it' |", command)

    def test_run_command_requires_a_command(self) -> None:
        declaration = {**HARBOR_DECLARATION, "command": []}

        with self.assertRaisesRegex(Exception, "has no command"):
            declared_support.run_command(declaration, model="m", instruction="x")

    def test_install_commands_verify_and_chmod(self) -> None:
        commands = declared_support.install_commands(HARBOR_DECLARATION)

        self.assertIn(
            "sha256sum /installed-agent/bin/yach | grep -q " + "a" * 64,
            commands[0].replace("'", ""),
        )
        self.assertEqual(commands[1], "chmod 0755 /installed-agent/bin/yach")

    def test_validate_evidence_and_context_fields(self) -> None:
        evidence = declared_support.validate_evidence(dict(VALID_EVIDENCE))

        fields = declared_support.context_fields(evidence)
        self.assertEqual(fields["n_input_tokens"], 120)
        self.assertEqual(fields["n_output_tokens"], 30)
        self.assertEqual(fields["cost_usd"], 0.004)

    def test_validate_evidence_rejects_missing_usage(self) -> None:
        evidence = {k: v for k, v in VALID_EVIDENCE.items() if k != "usage"}

        with self.assertRaisesRegex(Exception, "usage"):
            declared_support.validate_evidence(evidence)


class DeclaredHarborJobTests(unittest.TestCase):
    def _config(self, root: Path) -> Path:
        artifact = root / "dist" / "yach"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"fake-binary")
        import hashlib

        sha256 = hashlib.sha256(b"fake-binary").hexdigest()
        config = f"""
[regatta]
name = "declared-harbor-smoke"

[course]
name = "team-evals"

[[course.tasks]]
id = "hello-task"
title = "Greet the user"

[course.adapter]
kind = "custom-eval"
dataset = "evals"
split = "v1"
harness = "harbor"

[harnesses.yach]
prompt = "argument"
evidence = "file"
command = ["yach", "run", "--model", "{{model}}"]

[harnesses.yach.install]
path = "dist/yach"
sha256 = "{sha256}"

[runtimes.harbor-yach]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "yach"
harness_version = "0.1.0"

[[vessels]]
name = "yach-baseline"
model = "claude-haiku-4-5"
runtime = "harbor-yach"

[[vessels]]
name = "yach-candidate"
model = "claude-haiku-4-5"
runtime = "harbor-yach"

[[comparisons]]
name = "baseline-vs-candidate"
course = "team-evals"
vessels = ["yach-baseline", "yach-candidate"]
"""
        tasks_dir = root / "evals" / "hello-task"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        (tasks_dir / "instruction.md").write_text("Greet.", encoding="utf-8")
        config_path = root / "regatta.toml"
        config_path.write_text(config, encoding="utf-8")
        return config_path

    def test_renders_declared_agent_job(self) -> None:
        from yacht.courses.terminal_bench.harness import harbor_run_config
        from yacht.courses.terminal_bench.job import render_terminal_bench_job

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = self._config(root)
            regatta = load_regatta(config_path)

            job = render_terminal_bench_job(
                regatta=regatta, vessel_name="yach-baseline"
            )

            agent = job["agent"]
            self.assertEqual(
                agent["import_path"], "yacht_harbor_agents.agents:YachtDeclared"
            )
            declaration = agent["declaration"]
            self.assertEqual(declaration["name"], "yach")
            self.assertEqual(
                declaration["install"]["path"],
                str((root / "dist" / "yach").resolve()),
            )

            harbor_config = harbor_run_config(job, trials_dir=root / "trials")
            kwargs = harbor_config["agents"][0]["kwargs"]
            self.assertEqual(kwargs["declaration"]["name"], "yach")

    def test_rejects_declared_harness_without_install_on_harbor(self) -> None:
        from yacht.courses.terminal_bench.job import render_terminal_bench_job

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = self._config(root)
            config = config_path.read_text(encoding="utf-8")
            config = config.replace(
                '[harnesses.yach.install]\npath = "dist/yach"\n', ""
            )
            # remove the install table entirely
            lines = [
                line
                for line in config.splitlines()
                if not line.startswith("sha256 = ")
                and line != "[harnesses.yach.install]"
                and not line.startswith("path = ")
            ]
            config_path.write_text("\n".join(lines), encoding="utf-8")
            regatta = load_regatta(config_path)

            with self.assertRaisesRegex(ConfigError, "must set a pinned install"):
                render_terminal_bench_job(regatta=regatta, vessel_name="yach-baseline")

    def test_harbor_command_mounts_the_artifact(self) -> None:
        from yacht.courses.terminal_bench.harness import harbor_command

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "yach"
            artifact.write_bytes(b"x")

            command = harbor_command(
                root / "config.json",
                trials_dir=root / "trials",
                secret_env=[],
                artifact_path=artifact,
            )

            self.assertIn(f"{artifact}:{artifact}", command)


class DeclaredEvidenceBackendTests(unittest.TestCase):
    def test_rejects_file_evidence_on_container_runtimes(self) -> None:
        config = DECLARED_CONFIG.replace(
            '[runtimes.yach-host]\nbackend = "host-nix"\nflake = "path:."\ncommand = ["yach", "run"]\nharness = "yach"',
            '[runtimes.yach-host]\nbackend = "container"\nimage = "yach-runtime:0.1.0"\ncommand = ["yach", "run"]\nharness = "yach"',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "does not reach container runtimes yet",
            ):
                load_regatta(config_path)

    def test_allows_stdout_evidence_on_container_runtimes(self) -> None:
        config = DECLARED_CONFIG.replace(
            'evidence = "file"', 'evidence = "stdout"'
        ).replace(
            '[runtimes.yach-host]\nbackend = "host-nix"\nflake = "path:."\ncommand = ["yach", "run"]\nharness = "yach"',
            '[runtimes.yach-host]\nbackend = "container"\nimage = "yach-runtime:0.1.0"\ncommand = ["yach", "run"]\nharness = "yach"',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")

            load_regatta(config_path)


class ContainerMountPathTests(unittest.TestCase):
    def test_relative_instance_root_resolves_to_absolute_mount(self) -> None:
        import os

        from yacht.runtimes.container import resolve_container_runtime
        from yacht.domain.model import Course, Regatta, RuntimeRecipe, Vessel

        runtime = RuntimeRecipe(
            name="c",
            backend="container",
            command=("yach", "run"),
            image="img:1",
        )
        regatta = Regatta(
            name="r",
            course=Course(name="c", tasks=()),
            vessels=(Vessel(name="v", model="m", rigging=(), runtime="c"),),
            runtime_recipes={"c": runtime},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                resolution = resolve_container_runtime(
                    regatta=regatta,
                    vessel=regatta.vessels[0],
                    instance_root=Path("logbook/runtime/comp/v"),
                    workspace_path=Path(temp_dir),
                )
            finally:
                os.chdir(cwd)

        mounts = [
            arg for arg in resolution.command_prefix if arg.startswith("type=bind,")
        ]
        for mount in mounts:
            source = mount.split("source=", 1)[1].split(",", 1)[0]
            self.assertTrue(
                Path(source).is_absolute(),
                f"mount source not absolute: {mount}",
            )


NATIVE_OUTPUT = {
    "response": {"text": "done"},
    "usage": {"in": 120, "out": 30, "reported": True},
    "tools": ["read_file", {"name": "bash", "count": 3}],
    "model": "m-1",
}

EVIDENCE_MAP = {
    "response": "response.text",
    "input_tokens": "usage.in",
    "output_tokens": "usage.out",
    "tool_calls": "tools",
    "model": "model",
    "usage_reported": "usage.reported",
}


class EvidenceMapTests(unittest.TestCase):
    def test_maps_native_output_to_normal_form(self) -> None:
        from yacht.harnesses.evidence_map import map_native_evidence

        document = map_native_evidence(EVIDENCE_MAP, NATIVE_OUTPUT)

        self.assertEqual(document["response"], "done")
        self.assertEqual(document["usage"]["input_tokens"], 120)
        self.assertEqual(document["usage"]["reported"], True)
        self.assertEqual(
            document["tool_calls"],
            [{"name": "read_file", "count": 1}, {"name": "bash", "count": 3}],
        )
        validate_harness_evidence_document(document)

    def test_missing_mapped_path_fails_loudly(self) -> None:
        from yacht.harnesses.evidence_map import map_native_evidence

        with self.assertRaisesRegex(SchemaValidationError, "missing mapped"):
            map_native_evidence(EVIDENCE_MAP, {"response": {"text": "x"}})

    def test_harbor_twin_matches(self) -> None:
        document = declared_support.normalize_evidence(
            {"evidence_map": EVIDENCE_MAP}, NATIVE_OUTPUT
        )
        self.assertEqual(document["usage"]["output_tokens"], 30)

    def test_config_rejects_unknown_map_keys(self) -> None:
        config = DECLARED_CONFIG.replace(
            "[harnesses.yach]",
            "[harnesses.yach.evidence_map]\n"
            'response = "r"\ninput_tokens = "i"\noutput_tokens = "o"\n'
            'sponsor = "x"\n\n[harnesses.yach]',
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "not a mappable evidence field"):
                load_regatta(config_path)

    def test_adapter_marks_unreported_usage(self) -> None:
        import json as json_module

        native = dict(NATIVE_OUTPUT)
        native["usage"] = {"in": 0, "out": 0, "reported": False}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = _write_harness_script(
                root, f"echo '{json_module.dumps(native)}'\n"
            )
            adapter = DeclaredHarnessAdapter(
                HarnessDeclaration(name="fake", evidence_map=EVIDENCE_MAP)
            )
            result = adapter.run_task(
                instance=_instance(root, script),
                task=_task(),
                prompt="p",
                env={"PATH": "/usr/bin:/bin"},
                cwd=root / "workspace",
                transcript_path=root / "t" / "task-1.json",
            )
        self.assertEqual(result.metrics.usage_source, "unreported")
        self.assertEqual(result.metrics.tokens, 0)


class AgentPromptDeterminismTests(unittest.TestCase):
    def _check(self, **kwargs):
        from yacht.preflight.execution import (
            AgentPromptResult,
            EffectiveCheck,
            _execute_agent_prompt_check,
        )
        from yacht.domain.model import PreflightCheck

        check = EffectiveCheck(
            check=PreflightCheck(name="c", kind="agent-prompt", prompt="p", **kwargs),
            required=True,
            origin="runtime",
            origin_name="r",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = _instance(root, root / "unused.sh")
            return _execute_agent_prompt_check(
                check,
                instance,
                lambda prompt, env, cwd: AgentPromptResult(
                    exit_code=0, response="ready to sail", tool_calls=()
                ),
            )

    def test_non_json_response_passes_by_default(self) -> None:
        result = self._check()
        self.assertEqual(result["status"], "passed")
        self.assertIn("response_contract_errors", result["evidence"])

    def test_expect_response_contains_is_enforced(self) -> None:
        result = self._check(expect_response_contains=("ready",))
        self.assertEqual(result["status"], "passed")
        failing = self._check(expect_response_contains=("anchored",))
        self.assertEqual(failing["status"], "failed")
        self.assertEqual(failing["evidence"]["missing_response_contains"], ["anchored"])


if __name__ == "__main__":
    unittest.main()
