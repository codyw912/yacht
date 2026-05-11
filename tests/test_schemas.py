import json
import tempfile
import unittest
from pathlib import Path

from yacht.regatta import ConfigError, run_regatta
from yacht.schemas import (
    BENCHMARK_EXECUTION_PLAN_SCHEMA,
    BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
    BENCHMARK_SCORECARD_SCHEMA,
    COURSE_HANDOFF_SCHEMA,
    PREFLIGHT_SCHEMA,
    PREFLIGHT_SUMMARY_SCHEMA,
    REGATTA_SCHEMA,
    SCORECARD_SCHEMA,
    WAKE_SCHEMA,
    validate_benchmark_execution_plan_document,
    validate_benchmark_launcher_handoff_document,
    validate_benchmark_scorecard_document,
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
            COURSE_HANDOFF_SCHEMA,
            "yacht.swe-bench-grading.v1",
            BENCHMARK_SCORECARD_SCHEMA,
            BENCHMARK_EXECUTION_PLAN_SCHEMA,
            BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
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
            "runtime": "mock",
            "workspace_path": "/tmp/workspace",
            "temp_home": "/tmp/home",
            "command_prefix": ["mock"],
            "cleanup_paths": ["/tmp/home"],
            "status": "passed",
            "failure_policy": "abort-group",
            "secret_refs": [],
            "checks": [
                {
                    "name": "runtime-present",
                    "kind": "command",
                    "origin": "runtime",
                    "origin_name": "mock",
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
                            "evidence_artifact_path": "preflight/baseline.json",
                            "checks": [
                                {
                                    "name": "runtime-present",
                                    "kind": "command",
                                    "origin": "runtime",
                                    "origin_name": "mock",
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
                            "evidence_artifact_path": "preflight/baseline.json",
                            "checks": [
                                {
                                    "name": "runtime-present",
                                    "kind": "command",
                                    "origin": "runtime",
                                    "origin_name": "mock",
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

    def test_benchmark_scorecard_documents_include_schema_version(self) -> None:
        document = {
            "schema": BENCHMARK_SCORECARD_SCHEMA,
            "regatta": "pi-fff-comparison",
            "course": "swe-bench-lite",
            "adapter": {
                "kind": "swe-bench",
                "dataset": "princeton-nlp/SWE-bench_Lite",
                "split": "test",
            },
            "status": "partial",
            "comparisons": [
                {
                    "name": "pi-vs-pi-fff",
                    "course": "swe-bench-lite",
                    "vessels": [
                        {
                            "name": "pi-baseline",
                            "status": "missing",
                            "submitted_instances": 0,
                            "resolved_instances": 0,
                            "resolution_rate": 0.0,
                        },
                        {
                            "name": "pi-plus-fff",
                            "status": "measured",
                            "submitted_instances": 1,
                            "resolved_instances": 1,
                            "resolution_rate": 1.0,
                            "resolved_ids": ["django__django-11099"],
                            "unresolved_ids": [],
                        },
                    ],
                }
            ],
        }

        validate_benchmark_scorecard_document(document)

    def test_benchmark_scorecard_rejects_unknown_vessel_status(self) -> None:
        document = {
            "schema": BENCHMARK_SCORECARD_SCHEMA,
            "regatta": "pi-fff-comparison",
            "course": "swe-bench-lite",
            "adapter": {
                "kind": "swe-bench",
                "dataset": "princeton-nlp/SWE-bench_Lite",
                "split": "test",
            },
            "status": "partial",
            "comparisons": [
                {
                    "name": "pi-vs-pi-fff",
                    "course": "swe-bench-lite",
                    "vessels": [
                        {
                            "name": "pi-plus-fff",
                            "status": "unknown",
                            "submitted_instances": 1,
                            "resolved_instances": 1,
                            "resolution_rate": 1.0,
                        },
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(
            ValueError,
            "comparisons\\[0\\].vessels\\[0\\].status",
        ):
            validate_benchmark_scorecard_document(document)

    def test_benchmark_execution_plan_documents_include_schema_version(self) -> None:
        document = {
            "schema": BENCHMARK_EXECUTION_PLAN_SCHEMA,
            "regatta": "pi-fff-comparison",
            "course": "swe-bench-lite",
            "adapter": {
                "kind": "swe-bench",
                "dataset": "princeton-nlp/SWE-bench_Lite",
                "split": "test",
                "harness": "docker",
            },
            "status": "mixed",
            "comparisons": [
                {
                    "name": "pi-vs-pi-fff",
                    "course": "swe-bench-lite",
                    "status": "mixed",
                    "vessels": [
                        {
                            "name": "pi-baseline",
                            "status": "ready-for-grading",
                            "candidate_patches_path": "candidate-patches.jsonl",
                            "candidate_patches_present": True,
                            "grading_report_path": "grading-report.json",
                            "grading_report_present": False,
                            "preflight_artifact_path": "preflight/pi-baseline.json",
                            "preflight_artifact_present": True,
                            "preflight_status": "passed",
                        },
                        {
                            "name": "pi-plus-fff",
                            "status": "graded",
                            "candidate_patches_path": "candidate-patches.jsonl",
                            "candidate_patches_present": True,
                            "grading_report_path": "grading-report.json",
                            "grading_report_present": True,
                            "preflight_artifact_path": "preflight/pi-plus-fff.json",
                            "preflight_artifact_present": False,
                            "preflight_status": "missing",
                        },
                    ],
                }
            ],
        }

        validate_benchmark_execution_plan_document(document)

    def test_benchmark_launcher_handoff_documents_include_schema_version(self) -> None:
        document = {
            "schema": BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
            "regatta": "pi-fff-comparison",
            "course": "swe-bench-lite",
            "adapter": {
                "kind": "swe-bench",
                "dataset": "princeton-nlp/SWE-bench_Lite",
                "split": "test",
                "harness": "docker",
            },
            "status": "ready-to-launch",
            "comparisons": [
                {
                    "name": "pi-vs-pi-fff",
                    "course": "swe-bench-lite",
                    "status": "ready-to-launch",
                    "vessels": [
                        {
                            "name": "pi-baseline",
                            "status": "ready-to-launch",
                            "candidate_patches_path": "candidate-patches.jsonl",
                            "candidate_patches_present": True,
                            "expected_yacht_grading_report_path": "grading-report.json",
                            "grading_report_present": False,
                            "preflight_artifact_path": "preflight/pi-baseline.json",
                            "preflight_artifact_present": True,
                            "preflight_status": "passed",
                            "native_report_dir": "native-report",
                            "command": [
                                "python",
                                "-m",
                                "swebench.harness.run_evaluation",
                            ],
                            "command_preview": "python -m swebench.harness.run_evaluation",
                        },
                    ],
                }
            ],
        }

        validate_benchmark_launcher_handoff_document(document)

    def test_benchmark_launcher_handoff_rejects_unknown_vessel_status(self) -> None:
        document = {
            "schema": BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
            "regatta": "pi-fff-comparison",
            "course": "swe-bench-lite",
            "adapter": {
                "kind": "swe-bench",
                "dataset": "princeton-nlp/SWE-bench_Lite",
                "split": "test",
                "harness": "docker",
            },
            "status": "mixed",
            "comparisons": [
                {
                    "name": "pi-vs-pi-fff",
                    "course": "swe-bench-lite",
                    "status": "mixed",
                    "vessels": [
                        {
                            "name": "pi-plus-fff",
                            "status": "unknown",
                            "candidate_patches_path": "candidate-patches.jsonl",
                            "candidate_patches_present": True,
                            "expected_yacht_grading_report_path": "grading-report.json",
                            "grading_report_present": False,
                            "preflight_artifact_path": "preflight/pi-plus-fff.json",
                            "preflight_artifact_present": False,
                            "preflight_status": "missing",
                            "native_report_dir": "native-report",
                        },
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(
            ValueError,
            "comparisons\\[0\\].vessels\\[0\\].status",
        ):
            validate_benchmark_launcher_handoff_document(document)

    def test_benchmark_execution_plan_rejects_unknown_vessel_status(self) -> None:
        document = {
            "schema": BENCHMARK_EXECUTION_PLAN_SCHEMA,
            "regatta": "pi-fff-comparison",
            "course": "swe-bench-lite",
            "adapter": {
                "kind": "swe-bench",
                "dataset": "princeton-nlp/SWE-bench_Lite",
                "split": "test",
                "harness": "docker",
            },
            "status": "mixed",
            "comparisons": [
                {
                    "name": "pi-vs-pi-fff",
                    "course": "swe-bench-lite",
                    "status": "mixed",
                    "vessels": [
                        {
                            "name": "pi-plus-fff",
                            "status": "unknown",
                            "candidate_patches_path": "candidate-patches.jsonl",
                            "candidate_patches_present": True,
                            "grading_report_path": "grading-report.json",
                            "grading_report_present": True,
                            "preflight_artifact_path": "preflight/pi-plus-fff.json",
                            "preflight_artifact_present": False,
                            "preflight_status": "missing",
                        },
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(
            ValueError,
            "comparisons\\[0\\].vessels\\[0\\].status",
        ):
            validate_benchmark_execution_plan_document(document)

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
