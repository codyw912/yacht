import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError, run_regatta
from yacht.contracts.schemas import (
    BENCHMARK_EXECUTION_PLAN_SCHEMA,
    BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
    BENCHMARK_LAUNCH_RESULT_SCHEMA,
    BENCHMARK_READINESS_SUMMARY_SCHEMA,
    BENCHMARK_SCORECARD_SCHEMA,
    COURSE_HANDOFF_SCHEMA,
    PREFLIGHT_EVIDENCE_REPORT_SCHEMA,
    PREFLIGHT_SCHEMA,
    PREFLIGHT_SUMMARY_SCHEMA,
    REAL_BENCHMARK_RUNBOOK_SCHEMA,
    REAL_SMOKE_RUNBOOK_SCHEMA,
    REGATTA_SCHEMA,
    RUNTIME_INSTANCES_SCHEMA,
    SCORECARD_SCHEMA,
    SMOKE_READINESS_REPORT_SCHEMA,
    TASK_ATTEMPT_SCORECARD_SCHEMA,
    TASK_ATTEMPT_SCHEMA,
    WAKE_SCHEMA,
    validate_benchmark_execution_plan_document,
    validate_benchmark_launcher_handoff_document,
    validate_benchmark_launch_result_document,
    validate_benchmark_readiness_summary_document,
    validate_benchmark_scorecard_document,
    validate_preflight_document,
    validate_preflight_evidence_report_document,
    validate_preflight_summary_document,
    validate_real_benchmark_runbook_document,
    validate_real_smoke_runbook_document,
    validate_runtime_instances_document,
    validate_scorecard_document,
    validate_smoke_readiness_report_document,
    validate_task_attempt_scorecard_document,
    validate_task_attempt_document,
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
            "yacht.run-index.v1",
            SCORECARD_SCHEMA,
            PREFLIGHT_SCHEMA,
            PREFLIGHT_SUMMARY_SCHEMA,
            PREFLIGHT_EVIDENCE_REPORT_SCHEMA,
            COURSE_HANDOFF_SCHEMA,
            "yacht.custom-eval-grading.v1",
            "yacht.swe-bench-grading.v1",
            BENCHMARK_SCORECARD_SCHEMA,
            BENCHMARK_EXECUTION_PLAN_SCHEMA,
            BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
            BENCHMARK_LAUNCH_RESULT_SCHEMA,
            BENCHMARK_READINESS_SUMMARY_SCHEMA,
            RUNTIME_INSTANCES_SCHEMA,
            TASK_ATTEMPT_SCHEMA,
            TASK_ATTEMPT_SCORECARD_SCHEMA,
            SMOKE_READINESS_REPORT_SCHEMA,
            REAL_SMOKE_RUNBOOK_SCHEMA,
            REAL_BENCHMARK_RUNBOOK_SCHEMA,
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

    def test_runtime_instances_documents_include_schema_version(self) -> None:
        document = {
            "schema": RUNTIME_INSTANCES_SCHEMA,
            "regatta": "pi-fff-comparison",
            "course": "swe-bench-lite",
            "mode": "dry-run",
            "workspace_path": "/tmp/workspace",
            "comparisons": [
                {
                    "name": "pi-vs-pi-fff",
                    "course": "swe-bench-lite",
                    "vessels": [
                        {
                            "name": "pi-plus-fff",
                            "runtime": "pi",
                            "backend": "host-nix",
                            "harness": "pi",
                            "agent": "pi",
                            "trial_root": "/tmp/logbook/runtime/pi/pi-plus-fff",
                            "temp_home": "/tmp/logbook/runtime/pi/pi-plus-fff/home",
                            "workspace_path": "/tmp/workspace",
                            "command_prefix": ["nix", "develop", "flake", "--command"],
                            "command": ["pi"],
                            "env": {
                                "HOME": "/tmp/logbook/runtime/pi/pi-plus-fff/home",
                                "ANTHROPIC_API_KEY": "{secret:anthropic}",
                            },
                            "secret_refs": [
                                {
                                    "name": "anthropic",
                                    "source": "env",
                                    "ref": "ANTHROPIC_API_KEY",
                                    "redacted": True,
                                }
                            ],
                            "cleanup_paths": ["/tmp/logbook/runtime/pi/pi-plus-fff"],
                        }
                    ],
                }
            ],
        }

        validate_runtime_instances_document(document)

    def test_task_attempt_documents_include_schema_version(self) -> None:
        document = {
            "schema": TASK_ATTEMPT_SCHEMA,
            "regatta": "pi-fff-comparison",
            "course": "tiny-smoke-course",
            "comparison": "pi-vs-pi-fff",
            "vessel": "pi-plus-fff",
            "model": "pi",
            "rigging": ["fff"],
            "runtime": "pi-runtime",
            "status": "completed",
            "task": {
                "id": "task-1",
                "title": "Touch a marker file",
                "difficulty": 1,
            },
            "runtime_context": {
                "backend": "host-nix",
                "harness": "pi",
                "agent": "pi",
                "temp_home": "/tmp/yacht/home",
                "workspace_path": "/tmp/workspace",
                "command_prefix": ["nix", "develop", "flake", "--command"],
                "command": ["pi"],
                "cleanup_paths": ["/tmp/yacht"],
            },
            "prompt": "Create the requested marker file.",
            "agent": {
                "exit_code": 0,
                "response": "done",
                "tool_calls": ["fff"],
                "transcript_path": "/tmp/logbook/transcripts/task-1.json",
                "machine_evidence": {
                    "format": "pi-jsonl",
                    "event_count": 12,
                    "api": "anthropic-messages",
                    "provider": "anthropic",
                    "model": "claude-haiku-4-5",
                    "response_id": "msg_123",
                    "usage": {
                        "input": 1000,
                        "output": 234,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "totalTokens": 1234,
                    },
                    "cost": {"total": 0.00123},
                    "tool_calls": ["fff"],
                },
            },
            "metrics": {
                "tokens": 1234,
                "duration_seconds": 12.5,
            },
            "secret_refs": [
                {
                    "name": "anthropic",
                    "source": "env",
                    "ref": "ANTHROPIC_API_KEY",
                    "redacted": True,
                }
            ],
        }

        validate_task_attempt_document(document)

    def test_task_attempt_scorecard_documents_include_schema_version(self) -> None:
        document = {
            "schema": TASK_ATTEMPT_SCORECARD_SCHEMA,
            "regatta": "local-agent-preflight-smoke",
            "course": "local-smoke",
            "status": "complete",
            "summary": {
                "total_comparisons": 1,
                "total_vessels": 2,
                "total_attempts": 2,
                "completed_attempts": 2,
                "failed_attempts": 0,
                "total_tool_calls": 1,
                "tool_call_counts": {"local-smoke": 1},
                "total_tokens": 16,
                "total_cost": 0.00042,
                "total_duration_seconds": 0.0,
            },
            "comparisons": [
                {
                    "name": "local-agent-preflight",
                    "summary": {
                        "total_vessels": 2,
                        "total_attempts": 2,
                        "completed_attempts": 2,
                        "failed_attempts": 0,
                        "total_tool_calls": 1,
                        "tool_call_counts": {"local-smoke": 1},
                        "total_tokens": 16,
                        "total_cost": 0.00042,
                        "total_duration_seconds": 0.0,
                    },
                    "vessels": [
                        {
                            "name": "local-agent-with-tool",
                            "status": "measured",
                            "task_attempts": 1,
                            "completed_attempts": 1,
                            "failed_attempts": 0,
                            "success_rate": 1.0,
                            "harnesses": ["local-smoke"],
                            "tool_call_count": 1,
                            "tool_call_counts": {"local-smoke": 1},
                            "total_tokens": 8,
                            "total_cost": 0.00042,
                            "total_duration_seconds": 0.0,
                            "artifact_paths": [
                                "logbook/task-attempts/local-agent-preflight/local-agent-with-tool/local-smoke-1.json"
                            ],
                        },
                    ],
                }
            ],
        }

        validate_task_attempt_scorecard_document(document)

    def test_task_attempt_scorecard_rejects_invalid_tool_call_counts(self) -> None:
        document = {
            "schema": TASK_ATTEMPT_SCORECARD_SCHEMA,
            "regatta": "local-agent-preflight-smoke",
            "course": "local-smoke",
            "status": "complete",
            "summary": {
                "total_comparisons": 1,
                "total_vessels": 1,
                "total_attempts": 1,
                "completed_attempts": 1,
                "failed_attempts": 0,
                "total_tool_calls": 1,
                "tool_call_counts": {"local-smoke": -1},
                "total_tokens": 8,
                "total_cost": 0.00042,
                "total_duration_seconds": 0.0,
            },
            "comparisons": [
                {
                    "name": "local-agent-preflight",
                    "summary": {
                        "total_vessels": 1,
                        "total_attempts": 1,
                        "completed_attempts": 1,
                        "failed_attempts": 0,
                        "total_tool_calls": 1,
                        "tool_call_counts": {"local-smoke": 1},
                        "total_tokens": 8,
                        "total_cost": 0.00042,
                        "total_duration_seconds": 0.0,
                    },
                    "vessels": [
                        {
                            "name": "local-agent-with-tool",
                            "status": "measured",
                            "task_attempts": 1,
                            "completed_attempts": 1,
                            "failed_attempts": 0,
                            "success_rate": 1.0,
                            "tool_call_count": 1,
                            "tool_call_counts": {"local-smoke": 1},
                            "total_tokens": 8,
                            "total_cost": 0.00042,
                            "total_duration_seconds": 0.0,
                            "artifact_paths": [
                                "logbook/task-attempts/local-agent-preflight/local-agent-with-tool/local-smoke-1.json"
                            ],
                        },
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "summary.tool_call_counts.local-smoke"):
            validate_task_attempt_scorecard_document(document)

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

    def test_smoke_readiness_report_documents_include_schema_version(self) -> None:
        document = {
            "schema": SMOKE_READINESS_REPORT_SCHEMA,
            "regatta": "pi-fff-comparison",
            "course": "swe-bench-lite",
            "status": "ready",
            "summary": {
                "total_vessels": 1,
                "ready_vessels": 1,
                "blocked_vessels": 0,
                "passed_preflight_vessels": 1,
                "completed_task_attempt_vessels": 1,
                "passed_agent_prompt_checks": 1,
            },
            "comparisons": [
                {
                    "name": "pi-vs-pi-fff",
                    "status": "ready",
                    "vessels": [
                        {
                            "name": "pi-plus-fff",
                            "status": "ready",
                            "preflight_status": "passed",
                            "task_attempt_status": "measured",
                            "preflight_artifact_path": (
                                "logbook/preflight/pi-vs-pi-fff/pi-plus-fff.json"
                            ),
                            "task_attempt_artifact_paths": [
                                "logbook/task-attempts/pi-vs-pi-fff/pi-plus-fff/task.json"
                            ],
                            "agent_prompt_checks": {
                                "total": 1,
                                "passed": 1,
                            },
                            "tool_call_counts": {"fffind": 1},
                            "expected_tool_calls": ["fffind"],
                            "missing_expected_tool_calls": [],
                            "reasons": [],
                        }
                    ],
                }
            ],
        }

        validate_smoke_readiness_report_document(document)

    def test_real_smoke_runbook_documents_include_schema_version(self) -> None:
        document = {
            "schema": REAL_SMOKE_RUNBOOK_SCHEMA,
            "regatta": "pi-fff-comparison",
            "course": "swe-bench-lite",
            "agent": "pi",
            "secret_placeholders": [
                {
                    "name": "anthropic",
                    "source": "env",
                    "ref": "ANTHROPIC_API_KEY",
                    "argument": '--secret anthropic="$ANTHROPIC_API_KEY"',
                }
            ],
            "steps": [
                {
                    "name": "real-smoke-eval",
                    "command": "uv run yacht real-smoke-eval regatta.toml",
                    "artifacts": ["logbook/smoke-readiness-report.json"],
                }
            ],
            "artifacts": {
                "preflight": ["logbook/preflight/pi-vs-pi-fff/pi-plus-fff.json"],
                "task_attempts": [
                    "logbook/task-attempts/pi-vs-pi-fff/pi-plus-fff/task.json"
                ],
                "task_attempt_scorecard": "logbook/task-attempt-scorecard.json",
                "smoke_readiness_report": "logbook/smoke-readiness-report.json",
                "smoke_report": "logbook/smoke-report.txt",
                "real_smoke_runbook": "logbook/real-smoke-runbook.json",
            },
        }

        validate_real_smoke_runbook_document(document)

    def test_real_benchmark_runbook_documents_include_schema_version(self) -> None:
        document = {
            "schema": REAL_BENCHMARK_RUNBOOK_SCHEMA,
            "regatta": "container-pi-fff-real-benchmark-smoke",
            "course": "swe-bench-lite",
            "agent": "pi",
            "secret_placeholders": [
                {
                    "name": "anthropic",
                    "source": "env",
                    "ref": "ANTHROPIC_API_KEY",
                    "argument": "--secret anthropic=@env:ANTHROPIC_API_KEY",
                }
            ],
            "steps": [
                {
                    "name": "real-benchmark-eval",
                    "command": "uv run yacht real-benchmark-eval regatta.toml",
                    "artifacts": ["logbook/benchmark-scorecard.json"],
                }
            ],
            "artifacts": {
                "course_handoff": "logbook/course-handoff.json",
                "preflight": ["logbook/preflight/pi-vs-pi-fff/pi-plus-fff.json"],
                "preflight_evidence_report": (
                    "logbook/preflight-evidence-report.json"
                ),
                "task_attempts": [
                    "logbook/task-attempts/pi-vs-pi-fff/pi-plus-fff/task.json"
                ],
                "task_attempt_scorecard": "logbook/task-attempt-scorecard.json",
                "candidate_patches": [
                    "logbook/course-handoff/swe-bench/vessels/pi-plus-fff/"
                    "candidate-patches.jsonl"
                ],
                "runtime_instances": "logbook/runtime-instances.json",
                "benchmark_execution_plan": "logbook/benchmark-execution-plan.json",
                "benchmark_launcher_handoff": (
                    "logbook/benchmark-launcher-handoff.json"
                ),
                "benchmark_launch_result": "logbook/benchmark-launch-result.json",
                "benchmark_grading_collection": (
                    "logbook/benchmark-grading-collection.json"
                ),
                "benchmark_scorecard": "logbook/benchmark-scorecard.json",
                "benchmark_report": "logbook/benchmark-report.md",
                "real_benchmark_eval": "logbook/real-benchmark-eval.json",
                "real_benchmark_runbook": "logbook/real-benchmark-runbook.json",
            },
        }

        validate_real_benchmark_runbook_document(document)

    def test_benchmark_launch_result_documents_include_schema_version(self) -> None:
        document = {
            "schema": BENCHMARK_LAUNCH_RESULT_SCHEMA,
            "regatta": "pi-fff-comparison",
            "course": "swe-bench-lite",
            "adapter": {
                "kind": "swe-bench",
                "dataset": "princeton-nlp/SWE-bench_Lite",
                "split": "test",
                "harness": "docker",
            },
            "status": "complete",
            "summary": {
                "total_vessels": 1,
                "launched_vessels": 1,
                "completed_launches": 1,
                "failed_launches": 0,
                "skipped_vessels": 0,
            },
            "comparisons": [
                {
                    "name": "pi-vs-pi-fff",
                    "course": "swe-bench-lite",
                    "status": "complete",
                    "vessels": [
                        {
                            "name": "pi-baseline",
                            "status": "completed",
                            "launcher_status": "ready-to-launch",
                            "command": [
                                "python",
                                "-m",
                                "swebench.harness.run_evaluation",
                            ],
                            "command_preview": (
                                "python -m swebench.harness.run_evaluation"
                            ),
                            "exit_code": 0,
                            "stdout_path": "logbook/benchmark-launch/stdout.txt",
                            "stderr_path": "logbook/benchmark-launch/stderr.txt",
                            "native_report_dir": "logbook/native-report",
                            "expected_native_report_path": (
                                "logbook/native-report/pi-baseline.run-id.json"
                            ),
                            "expected_yacht_grading_report_path": (
                                "logbook/course-handoff/swe-bench/vessels/"
                                "pi-baseline/grading-report.json"
                            ),
                        }
                    ],
                }
            ],
        }

        validate_benchmark_launch_result_document(document)

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

    def test_preflight_evidence_report_documents_include_schema_version(self) -> None:
        document = {
            "schema": PREFLIGHT_EVIDENCE_REPORT_SCHEMA,
            "regatta": "schema-smoke-test",
            "course": "tiny-course",
            "status": "blocked",
            "comparisons": [
                {
                    "name": "baseline-vs-rigged",
                    "course": "tiny-course",
                    "status": "blocked",
                    "vessels": [
                        {
                            "name": "baseline",
                            "status": "eligible",
                            "eligible_for_benchmark": True,
                            "reason": "preflight-passed",
                            "preflight_artifact_path": "preflight/baseline.json",
                            "preflight_artifact_present": True,
                            "preflight_status": "passed",
                        },
                        {
                            "name": "rigged",
                            "status": "missing-preflight",
                            "eligible_for_benchmark": False,
                            "reason": "preflight-missing",
                            "preflight_artifact_path": "preflight/rigged.json",
                            "preflight_artifact_present": False,
                            "preflight_status": "missing",
                        },
                    ],
                }
            ],
        }

        validate_preflight_evidence_report_document(document)

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
        document = _valid_benchmark_scorecard_document()

        validate_benchmark_scorecard_document(document)

    def test_benchmark_scorecard_requires_top_level_summary(self) -> None:
        document = _valid_benchmark_scorecard_document()
        del document["summary"]

        with self.assertRaisesRegex(ValueError, "benchmark scorecard.summary"):
            validate_benchmark_scorecard_document(document)

    def test_benchmark_scorecard_requires_comparison_delta(self) -> None:
        document = _valid_benchmark_scorecard_document()
        del document["comparisons"][0]["delta"]

        with self.assertRaisesRegex(ValueError, "comparisons\\[0\\].delta"):
            validate_benchmark_scorecard_document(document)

    def test_benchmark_scorecard_rejects_inconsistent_comparison_summary(
        self,
    ) -> None:
        document = _valid_benchmark_scorecard_document()
        document["comparisons"][0]["summary"]["measured_vessels"] = 2

        with self.assertRaisesRegex(
            ValueError,
            "comparisons\\[0\\].summary.measured_vessels",
        ):
            validate_benchmark_scorecard_document(document)

    def test_benchmark_scorecard_rejects_inconsistent_comparison_delta(
        self,
    ) -> None:
        document = _valid_benchmark_scorecard_document()
        document["comparisons"][0]["delta"]["resolved_instances_delta"] = 2

        with self.assertRaisesRegex(
            ValueError,
            "comparisons\\[0\\].delta.resolved_instances_delta",
        ):
            validate_benchmark_scorecard_document(document)

    def test_benchmark_scorecard_rejects_inconsistent_top_level_summary(
        self,
    ) -> None:
        document = _valid_benchmark_scorecard_document()
        document["summary"]["missing_result_vessels"] = 0

        with self.assertRaisesRegex(
            ValueError,
            "benchmark scorecard.summary.missing_result_vessels",
        ):
            validate_benchmark_scorecard_document(document)

    def test_benchmark_scorecard_rejects_unknown_vessel_status(self) -> None:
        document = _valid_benchmark_scorecard_document()
        document["comparisons"][0]["vessels"][0]["status"] = "unknown"

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
                            "runtime_instances_artifact_path": "runtime-instances.json",
                            "runtime_instances_artifact_present": True,
                            "runtime_snapshot_status": "matched",
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
                            "runtime_instances_artifact_path": "runtime-instances.json",
                            "runtime_instances_artifact_present": True,
                            "runtime_snapshot_status": "matched",
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
                            "runtime_instances_artifact_path": "runtime-instances.json",
                            "runtime_instances_artifact_present": True,
                            "runtime_snapshot_status": "matched",
                            "native_report_dir": "native-report",
                            "expected_native_report_path": (
                                "native-report/pi-baseline.run-id.json"
                            ),
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
                            "runtime_instances_artifact_path": "runtime-instances.json",
                            "runtime_instances_artifact_present": False,
                            "runtime_snapshot_status": "missing",
                            "native_report_dir": "native-report",
                            "expected_native_report_path": (
                                "native-report/pi-plus-fff.run-id.json"
                            ),
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
                            "runtime_instances_artifact_path": "runtime-instances.json",
                            "runtime_instances_artifact_present": False,
                            "runtime_snapshot_status": "missing",
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

    def test_benchmark_readiness_summary_documents_include_schema_version(
        self,
    ) -> None:
        document = _valid_benchmark_readiness_summary_document()

        validate_benchmark_readiness_summary_document(document)

    def test_benchmark_readiness_summary_rejects_inconsistent_blocked_count(
        self,
    ) -> None:
        document = _valid_benchmark_readiness_summary_document()
        document["blocked_vessel_count"] = 2

        with self.assertRaisesRegex(
            ValueError,
            "blocked_vessel_count must equal blocked_vessels length",
        ):
            validate_benchmark_readiness_summary_document(document)

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


def _valid_benchmark_scorecard_document() -> dict[str, Any]:
    return {
        "schema": BENCHMARK_SCORECARD_SCHEMA,
        "regatta": "pi-fff-comparison",
        "course": "swe-bench-lite",
        "adapter": {
            "kind": "swe-bench",
            "dataset": "princeton-nlp/SWE-bench_Lite",
            "split": "test",
        },
        "status": "partial",
        "summary": {
            "total_comparisons": 1,
            "total_vessels": 2,
            "eligible_vessels": 1,
            "blocked_vessels": 1,
            "measured_vessels": 1,
            "missing_result_vessels": 1,
        },
        "comparisons": [
            {
                "name": "pi-vs-pi-fff",
                "course": "swe-bench-lite",
                "summary": {
                    "total_vessels": 2,
                    "eligible_vessels": 1,
                    "blocked_vessels": 1,
                    "measured_vessels": 1,
                    "missing_result_vessels": 1,
                },
                "delta": {
                    "baseline_vessel": "pi-baseline",
                    "challenger_vessel": "pi-plus-fff",
                    "resolved_instances_delta": 1,
                    "resolution_rate_delta": 1.0,
                },
                "vessels": [
                    {
                        "name": "pi-baseline",
                        "status": "missing",
                        "submitted_instances": 0,
                        "resolved_instances": 0,
                        "resolution_rate": 0.0,
                        "eligible_for_benchmark": False,
                        "preflight_status": "missing",
                        "preflight_reason": "preflight-missing",
                        "preflight_artifact_path": "preflight/pi-baseline.json",
                    },
                    {
                        "name": "pi-plus-fff",
                        "status": "measured",
                        "submitted_instances": 1,
                        "resolved_instances": 1,
                        "resolution_rate": 1.0,
                        "resolved_ids": ["django__django-11099"],
                        "unresolved_ids": [],
                        "eligible_for_benchmark": True,
                        "preflight_status": "passed",
                        "preflight_reason": "preflight-passed",
                        "preflight_artifact_path": "preflight/pi-plus-fff.json",
                    },
                ],
            }
        ],
    }


def _valid_benchmark_readiness_summary_document() -> dict[str, Any]:
    return {
        "schema": BENCHMARK_READINESS_SUMMARY_SCHEMA,
        "regatta": "pi-fff-comparison",
        "course": "swe-bench-lite",
        "status": "mixed",
        "total_vessels": 2,
        "launchable_vessels": 0,
        "graded_vessels": 1,
        "blocked_vessel_count": 1,
        "blocked_vessels": [
            {
                "comparison": "pi-vs-pi-fff",
                "vessel": "pi-baseline",
                "status": "missing-runtime-snapshot",
                "details": "runtime instances: runtime-instances.json",
                "artifact_paths": {
                    "candidate_patches": "candidate-patches.jsonl",
                    "preflight": "preflight/pi-baseline.json",
                    "runtime_instances": "runtime-instances.json",
                    "grading_report": "grading-report.json",
                },
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
