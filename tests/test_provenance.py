import unittest
from pathlib import Path

from yacht import __version__
from yacht.contracts.schemas import SchemaValidationError
from yacht.contracts.schemas import validate_task_attempt_document
from yacht.domain.model import (
    Course,
    Regatta,
    RiggingInstallStep,
    RiggingRecipe,
    RuntimeInstance,
    RuntimeRecipe,
    Vessel,
)
from yacht.workflows.provenance import build_provenance


def _regatta(riggings: dict[str, RiggingRecipe]) -> Regatta:
    return Regatta(
        name="provenance-test",
        course=Course(name="tiny-course", tasks=()),
        vessels=(),
        rigging_recipes=riggings,
    )


def _instance(runtime: RuntimeRecipe) -> RuntimeInstance:
    return RuntimeInstance(
        runtime=runtime,
        temp_home=Path("/tmp/home"),
        workspace_path=Path("/tmp/workspace"),
        env={},
        command_prefix=(),
        cleanup_paths=(),
    )


def _claude_code_runtime() -> RuntimeRecipe:
    return RuntimeRecipe(
        name="claude-code-container",
        backend="container",
        harness="claude-code",
        image="yacht/claude-code-runtime:claude-2.1.211",
        command=("claude",),
    )


class BuildProvenanceTests(unittest.TestCase):
    def test_resolves_all_fields_from_available_evidence(self) -> None:
        rigging = RiggingRecipe(
            name="fff-mcp",
            tools=("fff",),
            install=(
                RiggingInstallStep(
                    method="package",
                    target="npm:@ff-labs/mcp-fff@0.3.0",
                ),
                RiggingInstallStep(
                    method="mcp-server",
                    target="fff",
                    command=("mcp-fff", "--stdio"),
                ),
            ),
        )
        vessel = Vessel(
            name="rigged",
            model="claude-haiku-4-5",
            rigging=("fff-mcp",),
            runtime="claude-code-container",
        )

        provenance = build_provenance(
            regatta=_regatta({"fff-mcp": rigging}),
            vessel=vessel,
            instance=_instance(_claude_code_runtime()),
            machine_evidence={"model": "claude-haiku-4-5-20251001"},
        )

        self.assertEqual(
            provenance,
            {
                "yacht": {"version": __version__},
                "harness": {"name": "claude-code", "version": "2.1.211"},
                "model": {
                    "configured": "claude-haiku-4-5",
                    "resolved": "claude-haiku-4-5-20251001",
                },
                "runtime": {
                    "backend": "container",
                    "image": "yacht/claude-code-runtime:claude-2.1.211",
                },
                "tools": [
                    {
                        "name": "fff-mcp",
                        "tools": ["fff"],
                        "version": "0.3.0",
                        "source": "npm:@ff-labs/mcp-fff@0.3.0",
                    }
                ],
            },
        )

    def test_records_null_for_unresolvable_fields(self) -> None:
        runtime = RuntimeRecipe(
            name="claude-host",
            backend="host-nix",
            harness="claude-code",
            command=("claude",),
        )
        vessel = Vessel(name="baseline", model="mock", rigging=(), runtime="host")

        provenance = build_provenance(
            regatta=_regatta({}),
            vessel=vessel,
            instance=_instance(runtime),
            machine_evidence={},
        )

        self.assertIsNone(provenance["harness"]["version"])
        self.assertIsNone(provenance["model"]["resolved"])
        self.assertIsNone(provenance["runtime"]["image"])
        self.assertEqual(provenance["tools"], [])

    def test_image_tag_without_version_suffix_resolves_to_null(self) -> None:
        runtime = RuntimeRecipe(
            name="latest-image",
            backend="container",
            harness="claude-code",
            image="yacht/claude-code-runtime:latest",
            command=("claude",),
        )
        vessel = Vessel(name="baseline", model="mock", rigging=())

        provenance = build_provenance(
            regatta=_regatta({}),
            vessel=vessel,
            instance=_instance(runtime),
            machine_evidence={},
        )

        self.assertIsNone(provenance["harness"]["version"])

    def test_unpinned_install_target_resolves_no_tool_version(self) -> None:
        rigging = RiggingRecipe(
            name="pi-fff",
            tools=("fff",),
            install=(
                RiggingInstallStep(
                    method="agent-extension",
                    target="npm:@ff-labs/pi-fff",
                    agent="pi",
                ),
            ),
        )
        vessel = Vessel(name="rigged", model="haiku", rigging=("pi-fff",))

        provenance = build_provenance(
            regatta=_regatta({"pi-fff": rigging}),
            vessel=vessel,
            instance=_instance(_claude_code_runtime()),
            machine_evidence={},
        )

        self.assertEqual(
            provenance["tools"],
            [{"name": "pi-fff", "tools": ["fff"], "version": None, "source": None}],
        )

    def test_ambiguous_pins_are_not_resolved(self) -> None:
        rigging = RiggingRecipe(
            name="two-pins",
            tools=("one", "two"),
            install=(
                RiggingInstallStep(method="package", target="npm:tool-one@1.0.0"),
                RiggingInstallStep(method="package", target="npm:tool-two@2.0.0"),
            ),
        )
        vessel = Vessel(name="rigged", model="haiku", rigging=("two-pins",))

        provenance = build_provenance(
            regatta=_regatta({"two-pins": rigging}),
            vessel=vessel,
            instance=_instance(_claude_code_runtime()),
            machine_evidence={},
        )

        self.assertEqual(provenance["tools"][0]["version"], None)
        self.assertEqual(provenance["tools"][0]["source"], None)


class ProvenanceSchemaTests(unittest.TestCase):
    def test_task_attempt_without_provenance_remains_valid(self) -> None:
        document = _valid_task_attempt()
        document.pop("provenance")

        validate_task_attempt_document(document)

    def test_rejects_provenance_missing_required_blocks(self) -> None:
        document = _valid_task_attempt()
        del document["provenance"]["model"]

        with self.assertRaisesRegex(SchemaValidationError, "provenance"):
            validate_task_attempt_document(document)

    def test_rejects_empty_string_where_null_or_value_is_required(self) -> None:
        document = _valid_task_attempt()
        document["provenance"]["harness"]["version"] = ""

        with self.assertRaisesRegex(
            SchemaValidationError,
            "provenance.harness.version",
        ):
            validate_task_attempt_document(document)

    def test_accepts_null_resolved_fields(self) -> None:
        document = _valid_task_attempt()
        document["provenance"]["harness"]["version"] = None
        document["provenance"]["model"]["resolved"] = None
        document["provenance"]["runtime"]["image"] = None

        validate_task_attempt_document(document)


def _valid_task_attempt() -> dict:
    return {
        "schema": "yacht.task-attempt.v1",
        "regatta": "provenance-test",
        "course": "tiny-course",
        "comparison": "a-vs-b",
        "vessel": "rigged",
        "model": "claude-haiku-4-5",
        "rigging": ["fff-mcp"],
        "runtime": "claude-code-container",
        "status": "completed",
        "task": {"id": "task-1", "title": "Fix the bug", "difficulty": 1},
        "provenance": {
            "yacht": {"version": "0.2.0"},
            "harness": {"name": "claude-code", "version": "2.1.211"},
            "model": {
                "configured": "claude-haiku-4-5",
                "resolved": "claude-haiku-4-5-20251001",
            },
            "runtime": {
                "backend": "container",
                "image": "yacht/claude-code-runtime:claude-2.1.211",
            },
            "tools": [
                {
                    "name": "fff-mcp",
                    "tools": ["fff"],
                    "version": "0.3.0",
                    "source": "npm:@ff-labs/mcp-fff@0.3.0",
                }
            ],
        },
        "runtime_context": {
            "backend": "container",
            "harness": "claude-code",
            "agent": "claude-code",
            "temp_home": "/tmp/home",
            "workspace_path": "/tmp/workspace",
            "command_prefix": ["docker", "run"],
            "command": ["claude"],
            "cleanup_paths": [],
            "setup_results": [],
        },
        "prompt": "Task ID: task-1\n",
        "agent": {
            "exit_code": 0,
            "response": "Done.",
            "tool_calls": ["Bash"],
            "transcript_path": "/tmp/transcript.json",
        },
        "metrics": {"tokens": 12, "duration_seconds": 1.5},
        "secret_refs": [],
    }


if __name__ == "__main__":
    unittest.main()
