import json
import tempfile
import unittest
from pathlib import Path

from yacht.regatta import ConfigError, run_regatta
from yacht.schemas import (
    PREFLIGHT_SCHEMA,
    PREFLIGHT_SUMMARY_SCHEMA,
    REGATTA_SCHEMA,
    SCORECARD_SCHEMA,
    WAKE_SCHEMA,
    validate_preflight_document,
    validate_preflight_summary_document,
    validate_scorecard_document,
    validate_wake_document,
)


VALID_REGATTA_CONFIG = """
[regatta]
name = "schema-smoke-test"

[course]
name = "tiny-course"
tasks = [
  { id = "task-1", title = "Fix a failing test", difficulty = 1 },
]

[[vessels]]
name = "baseline"
model = "mock-fast"
"""


INVALID_REGATTA_CONFIG = """
[regatta]
name = "schema-smoke-test"

[course]
name = "tiny-course"
tasks = []

[[vessels]]
name = "baseline"
model = "mock-fast"
"""


class SchemaTests(unittest.TestCase):
    def test_contract_schemas_are_json_schema_documents(self) -> None:
        schema_dir = Path("schemas")

        for schema_name in (
            REGATTA_SCHEMA,
            WAKE_SCHEMA,
            SCORECARD_SCHEMA,
            PREFLIGHT_SCHEMA,
            PREFLIGHT_SUMMARY_SCHEMA,
        ):
            schema_path = schema_dir / f"{schema_name}.schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))

            self.assertEqual(
                schema["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
            )
            self.assertEqual(
                schema["$id"],
                f"https://yacht.dev/schemas/{schema_name}.schema.json",
            )
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])

    def test_preflight_documents_include_schema_version(self) -> None:
        document = {
            "schema": PREFLIGHT_SCHEMA,
            "regatta": "schema-smoke-test",
            "vessel": "baseline",
            "status": "passed",
            "failure_policy": "abort-group",
            "secret_refs": [],
            "checks": [
                {
                    "name": "runtime-present",
                    "kind": "command",
                    "required": True,
                    "status": "passed",
                    "evidence": {"command": ["mock", "--version"]},
                }
            ],
        }

        validate_preflight_document(document)

    def test_preflight_summary_documents_include_schema_version(self) -> None:
        document = {
            "schema": PREFLIGHT_SUMMARY_SCHEMA,
            "regatta": "schema-smoke-test",
            "course": "tiny-course",
            "status": "passed",
            "preflight_failure_policy": "abort-group",
            "comparisons": [
                {
                    "name": "baseline-vs-rigged",
                    "status": "passed",
                    "vessels": [
                        {
                            "name": "baseline",
                            "status": "passed",
                            "checks": [
                                {
                                    "name": "runtime-present",
                                    "kind": "command",
                                    "required": True,
                                    "included": True,
                                    "status": "passed",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        validate_preflight_summary_document(document)

    def test_preflight_summary_rejects_unknown_check_status(self) -> None:
        document = {
            "schema": PREFLIGHT_SUMMARY_SCHEMA,
            "regatta": "schema-smoke-test",
            "course": "tiny-course",
            "status": "passed",
            "preflight_failure_policy": "abort-group",
            "comparisons": [
                {
                    "name": "baseline-vs-rigged",
                    "status": "passed",
                    "vessels": [
                        {
                            "name": "baseline",
                            "status": "passed",
                            "checks": [
                                {
                                    "name": "runtime-present",
                                    "kind": "command",
                                    "required": True,
                                    "included": True,
                                    "status": "unknown",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(
            ValueError,
            "comparisons\\[0\\].vessels\\[0\\].checks\\[0\\].status",
        ):
            validate_preflight_summary_document(document)

    def test_wake_and_scorecard_documents_include_schema_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / "regatta.toml"
            logbook_dir = workspace / "logbook"
            config_path.write_text(VALID_REGATTA_CONFIG, encoding="utf-8")

            scorecard = run_regatta(config_path, logbook_dir)
            wake_path = next((logbook_dir / "wake").glob("*.json"))
            wake = json.loads(wake_path.read_text(encoding="utf-8"))

            validate_scorecard_document(scorecard)
            validate_wake_document(wake)
            self.assertEqual(scorecard["schema"], SCORECARD_SCHEMA)
            self.assertEqual(wake["schema"], WAKE_SCHEMA)

    def test_invalid_regatta_config_fails_before_writing_logbook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / "regatta.toml"
            logbook_dir = workspace / "logbook"
            config_path.write_text(INVALID_REGATTA_CONFIG, encoding="utf-8")

            with self.assertRaisesRegex(
                ConfigError,
                "course.tasks must contain at least one task",
            ):
                run_regatta(config_path, logbook_dir)

            self.assertFalse(logbook_dir.exists())


if __name__ == "__main__":
    unittest.main()
