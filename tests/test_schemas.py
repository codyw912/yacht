import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from yacht.contracts.json_schema import schema_text
from yacht.contracts.schemas import (
    SchemaValidationError,
    BENCHMARK_AGGREGATE_SCHEMA,
    BENCHMARK_EXECUTION_PLAN_SCHEMA,
    BENCHMARK_GRADING_COLLECTION_SCHEMA,
    BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
    BENCHMARK_LAUNCH_RESULT_SCHEMA,
    BENCHMARK_READINESS_SUMMARY_SCHEMA,
    BENCHMARK_SCORECARD_SCHEMA,
    COURSE_HANDOFF_SCHEMA,
    PREFLIGHT_EVIDENCE_REPORT_SCHEMA,
    PREFLIGHT_SCHEMA,
    PREFLIGHT_SUMMARY_SCHEMA,
    REAL_BENCHMARK_EVAL_SCHEMA,
    REAL_BENCHMARK_REPETITIONS_SCHEMA,
    REAL_BENCHMARK_RUNBOOK_SCHEMA,
    REAL_SMOKE_RUNBOOK_SCHEMA,
    REGATTA_SCHEMA,
    RUN_INDEX_SCHEMA,
    RUN_INDEX_V2_SCHEMA,
    RUNTIME_INSTANCES_SCHEMA,
    SCORECARD_SCHEMA,
    SMOKE_READINESS_REPORT_SCHEMA,
    SWE_BENCH_GRADING_SCHEMA,
    TASK_ATTEMPT_SCORECARD_SCHEMA,
    TERMINAL_BENCH_JOB_SCHEMA,
    TASK_ATTEMPT_SCHEMA,
    WAKE_SCHEMA,
    validate_benchmark_aggregate_document,
    validate_benchmark_execution_plan_document,
    validate_benchmark_grading_collection_document,
    validate_benchmark_launcher_handoff_document,
    validate_benchmark_launch_result_document,
    validate_benchmark_readiness_summary_document,
    validate_benchmark_scorecard_document,
    validate_preflight_document,
    validate_preflight_evidence_report_document,
    validate_course_grading_report_document,
    validate_preflight_summary_document,
    validate_real_benchmark_eval_document,
    validate_real_benchmark_repetitions_document,
    validate_real_benchmark_runbook_document,
    validate_real_smoke_runbook_document,
    validate_run_index_document,
    validate_terminal_bench_job_document,
    validate_runtime_instances_document,
    validate_scorecard_document,
    validate_smoke_readiness_report_document,
    validate_task_attempt_scorecard_document,
    validate_task_attempt_document,
    validate_wake_document,
)
from yacht.domain.model import ConfigError, run_regatta


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


def _valid_wake_document() -> dict[str, Any]:
    return {
        "schema": WAKE_SCHEMA,
        "regatta": "schema-smoke-test",
        "course": "tiny-course",
        "vessel": "baseline",
        "model": "mock-fast",
        "rigging": [],
        "task_id": "task-1",
        "task_title": "Fix a failing test",
        "passed": True,
        "metrics": {
            "tokens": 42,
            "duration_seconds": 1.5,
            "usage_source": "reported",
        },
    }


class SchemaTests(unittest.TestCase):
    def test_contract_schemas_are_json_schema_documents(self) -> None:
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
            RUN_INDEX_V2_SCHEMA,
        ):
            schema = json.loads(schema_text(schema_name))

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

    def test_wake_schema_accepts_reported_usage_source(self) -> None:
        validate_wake_document(_valid_wake_document())

    def test_wake_schema_reports_missing_fields_with_document_path(self) -> None:
        document = _valid_wake_document()
        del document["course"]

        with self.assertRaisesRegex(
            SchemaValidationError,
            "wake: 'course' is a required property",
        ):
            validate_wake_document(document)

    def test_wake_schema_rejects_unknown_usage_source(self) -> None:
        document = _valid_wake_document()
        document["metrics"]["usage_source"] = "guessed"

        with self.assertRaisesRegex(
            SchemaValidationError,
            r"wake\.metrics\.usage_source: .*not one of",
        ):
            validate_wake_document(document)

    def test_wake_schema_rejects_unknown_fields(self) -> None:
        document = _valid_wake_document()
        document["unexpected"] = True

        with self.assertRaisesRegex(
            SchemaValidationError,
            "wake: Additional properties are not allowed",
        ):
            validate_wake_document(document)

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
        document = _valid_task_attempt_document()

        validate_task_attempt_document(document)

    def test_task_attempt_skill_stages_validate(self) -> None:
        document = _valid_task_attempt_document()
        document["agent"]["skill_stages"] = [
            {
                "skill": "team-conventions",
                "available": "unmeasured",
                "selected": "observed",
                "loaded": "unmeasured",
                "evidence_source": "claude-code-session-transcript",
            }
        ]

        validate_task_attempt_document(document)

    def test_task_attempt_skill_stages_require_evidence_source(self) -> None:
        document = _valid_task_attempt_document()
        document["agent"]["skill_stages"] = [
            {
                "skill": "team-conventions",
                "available": "unmeasured",
                "selected": "observed",
                "loaded": "unmeasured",
            }
        ]

        with self.assertRaisesRegex(ValueError, "evidence_source"):
            validate_task_attempt_document(document)

    def test_published_schema_declares_emitted_attempt_agent_keys(self) -> None:
        from yacht.courses.terminal_bench.attempts_from_trials import _agent_to_json

        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir)
            sessions = trial_dir / "agent" / "sessions" / "projects" / "-app"
            sessions.mkdir(parents=True)
            (sessions / "session.jsonl").write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Skill",
                                    "input": {"skill": "team-conventions"},
                                }
                            ]
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            agent = _agent_to_json(None, str(trial_dir), True)

        schema = json.loads(schema_text(TASK_ATTEMPT_SCHEMA))
        agent_schema = schema["$defs"]["agent"]
        self.assertFalse(agent_schema["additionalProperties"])
        declared = set(agent_schema["properties"])
        self.assertEqual(set(agent) - declared, set())
        for key in ("machine_evidence", "tool_call_evidence", "skill_stages"):
            self.assertIn(key, declared)
        self.assertIn("machine_evidence", agent)
        self.assertIn("tool_call_evidence", agent)
        self.assertIn("skill_stages", agent)

    def test_task_attempt_episodes_block_validates(self) -> None:
        document = _valid_task_attempt_document()
        document["episodes"] = {
            "count": 2,
            "to_resolution": 2,
            "items": [
                {
                    "index": 1,
                    "ended": "cap",
                    "started_at": "2026-08-02T00:00:00+00:00",
                    "finished_at": "2026-08-02T00:10:00+00:00",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                    "cost_usd": 0.4,
                },
                {"index": 2, "ended": "natural", "reward": 1.0},
            ],
        }

        validate_task_attempt_document(document)

    def test_task_attempt_episodes_rejects_count_mismatch(self) -> None:
        document = _valid_task_attempt_document()
        document["episodes"] = {
            "count": 3,
            "items": [{"index": 1, "ended": "natural"}],
        }

        with self.assertRaisesRegex(ValueError, "episodes.items must contain"):
            validate_task_attempt_document(document)

    def test_task_attempt_episodes_rejects_unknown_ended_value(self) -> None:
        document = _valid_task_attempt_document()
        document["episodes"] = {
            "count": 1,
            "items": [{"index": 1, "ended": "give-up"}],
        }

        with self.assertRaisesRegex(ValueError, "episodes.items\\[0\\].ended"):
            validate_task_attempt_document(document)

    def test_task_attempt_episodes_rejects_to_resolution_above_count(self) -> None:
        document = _valid_task_attempt_document()
        document["episodes"] = {
            "count": 1,
            "to_resolution": 2,
            "items": [{"index": 1, "ended": "natural"}],
        }

        with self.assertRaisesRegex(ValueError, "episodes.to_resolution"):
            validate_task_attempt_document(document)

    def test_task_attempt_episodes_rejects_negative_cost(self) -> None:
        document = _valid_task_attempt_document()
        document["episodes"] = {
            "count": 1,
            "items": [{"index": 1, "ended": "natural", "cost_usd": -0.1}],
        }

        with self.assertRaisesRegex(ValueError, "episodes.items\\[0\\].cost_usd"):
            validate_task_attempt_document(document)

    def test_task_attempt_episodes_rejects_non_object_item(self) -> None:
        document = _valid_task_attempt_document()
        document["episodes"] = {
            "count": 1,
            "items": ["not-an-object"],
        }

        with self.assertRaisesRegex(
            ValueError, "episodes.items\\[0\\] must be an object"
        ):
            validate_task_attempt_document(document)

    def test_task_attempt_scorecard_documents_include_schema_version(self) -> None:
        validate_task_attempt_scorecard_document(
            _valid_task_attempt_scorecard_document()
        )

    def test_task_attempt_scorecard_rejects_invalid_observed_tools(self) -> None:
        document = _valid_task_attempt_scorecard_document()
        vessel = document["comparisons"][0]["vessels"][1]
        vessel["tool_invocations"][0]["observed_tools"] = "fffind"

        with self.assertRaisesRegex(ValueError, "observed_tools"):
            validate_task_attempt_scorecard_document(document)

    def test_task_attempt_scorecard_rejects_comparison_summary_mismatch(self) -> None:
        document = _valid_task_attempt_scorecard_document()
        document["comparisons"][0]["summary"]["total_attempts"] = 3

        with self.assertRaisesRegex(
            ValueError, "comparisons\\[0\\].summary.total_attempts"
        ):
            validate_task_attempt_scorecard_document(document)

    def test_task_attempt_scorecard_rejects_top_level_summary_mismatch(self) -> None:
        document = _valid_task_attempt_scorecard_document()
        document["summary"]["total_tokens"] = 99

        with self.assertRaisesRegex(ValueError, "summary.total_tokens"):
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
                "total_distinct_tool_uses": 1,
                "attempts_by_tool": {"local-smoke": -1},
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
                        "total_distinct_tool_uses": 1,
                        "attempts_by_tool": {"local-smoke": 1},
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
                            "distinct_tool_uses": 1,
                            "attempts_by_tool": {"local-smoke": 1},
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

        with self.assertRaisesRegex(ValueError, "summary.attempts_by_tool.local-smoke"):
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
                            "attempts_by_tool": {"fffind": 1},
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
                    "command": "uv run yacht run regatta.toml",
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
                    "command": "uv run yacht run regatta.toml",
                    "artifacts": ["logbook/benchmark-scorecard.json"],
                }
            ],
            "artifacts": {
                "course_handoff": "logbook/course-handoff.json",
                "preflight": ["logbook/preflight/pi-vs-pi-fff/pi-plus-fff.json"],
                "preflight_evidence_report": ("logbook/preflight-evidence-report.json"),
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
        validate_benchmark_launch_result_document(
            _valid_benchmark_launch_result_document()
        )

    def test_launch_result_rejects_summary_that_contradicts_vessels(self) -> None:
        document = _valid_benchmark_launch_result_document()
        document["summary"]["completed_launches"] = 0
        document["summary"]["failed_launches"] = 1

        with self.assertRaisesRegex(ValueError, "summary.completed_launches"):
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

    def test_benchmark_scorecard_rejects_phantom_recorded_vessels(self) -> None:
        document = _valid_benchmark_scorecard_document()
        document["summary"]["recorded_vessels"] = 1

        with self.assertRaisesRegex(ValueError, "recorded_vessels"):
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


def _valid_task_attempt_document() -> dict[str, Any]:
    return {
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


def _valid_benchmark_launch_result_document() -> dict[str, Any]:
    return {
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


def _valid_task_attempt_scorecard_document() -> dict[str, Any]:
    return {
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
            "total_distinct_tool_uses": 1,
            "attempts_by_tool": {"local-smoke": 1},
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
                    "total_distinct_tool_uses": 1,
                    "attempts_by_tool": {"local-smoke": 1},
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
                        "distinct_tool_uses": 1,
                        "attempts_by_tool": {"local-smoke": 1},
                        "total_tokens": 8,
                        "total_cost": 0.00042,
                        "total_duration_seconds": 0.0,
                        "artifact_paths": [
                            "logbook/task-attempts/local-agent-preflight/local-agent-with-tool/local-smoke-1.json"
                        ],
                    },
                    {
                        "name": "local-agent-baseline",
                        "status": "measured",
                        "task_attempts": 1,
                        "completed_attempts": 1,
                        "failed_attempts": 0,
                        "success_rate": 1.0,
                        "harnesses": ["local-smoke"],
                        "distinct_tool_uses": 0,
                        "attempts_by_tool": {},
                        "total_tokens": 8,
                        "total_cost": 0.0,
                        "total_duration_seconds": 0.0,
                        "tool_invocations": [
                            {
                                "tool": "fff",
                                "kind": "mcp-server",
                                "expected_calls": ["mcp__fff__"],
                                "status": "measured",
                                "attempts": 1,
                                "measured_attempts": 1,
                                "invoked_attempts": 1,
                                "invocation_rate": 1.0,
                                "invocation_interval": {"low": 0.2, "high": 1.0},
                                "observed_tools": ["fffind"],
                            }
                        ],
                        "artifact_paths": [
                            "logbook/task-attempts/local-agent-preflight/local-agent-baseline/local-smoke-1.json"
                        ],
                    },
                ],
            }
        ],
    }


def _valid_benchmark_grading_collection_document() -> dict[str, Any]:
    return {
        "schema": BENCHMARK_GRADING_COLLECTION_SCHEMA,
        "regatta": "demo",
        "course": "demo-course",
        "adapter": {
            "kind": "swe-bench",
            "dataset": "princeton-nlp/SWE-bench_Lite",
            "split": "dev",
        },
        "status": "complete",
        "summary": {
            "total_vessels": 1,
            "completed_launches": 1,
            "collected_reports": 1,
            "missing_native_reports": 0,
            "invalid_native_reports": 0,
            "skipped_vessels": 0,
        },
        "next_steps": [],
        "comparisons": [
            {
                "name": "comparison",
                "course": "demo-course",
                "status": "complete",
                "vessels": [
                    {
                        "name": "baseline",
                        "launch_status": "completed",
                        "status": "collected",
                        "native_report_path": "/tmp/native-report.json",
                        "grading_report_path": "/tmp/grading-report.json",
                        "submitted_instances": 2,
                        "resolved_instances": 1,
                        "resolution_rate": 0.5,
                    }
                ],
            }
        ],
    }


class BenchmarkGradingCollectionSchemaTests(unittest.TestCase):
    def test_grading_collection_documents_include_schema_version(self) -> None:
        validate_benchmark_grading_collection_document(
            _valid_benchmark_grading_collection_document()
        )

    def test_grading_collection_requires_summary(self) -> None:
        document = _valid_benchmark_grading_collection_document()
        del document["summary"]

        with self.assertRaisesRegex(ValueError, "grading collection.summary"):
            validate_benchmark_grading_collection_document(document)

    def test_grading_collection_rejects_unknown_vessel_status(self) -> None:
        document = _valid_benchmark_grading_collection_document()
        document["comparisons"][0]["vessels"][0]["status"] = "graded"

        with self.assertRaisesRegex(ValueError, "vessels\\[0\\].status"):
            validate_benchmark_grading_collection_document(document)

    def test_grading_collection_requires_report_paths_when_collected(self) -> None:
        document = _valid_benchmark_grading_collection_document()
        del document["comparisons"][0]["vessels"][0]["grading_report_path"]

        with self.assertRaisesRegex(ValueError, "grading_report_path"):
            validate_benchmark_grading_collection_document(document)


def _valid_real_benchmark_repetitions_document() -> dict[str, Any]:
    return {
        "schema": REAL_BENCHMARK_REPETITIONS_SCHEMA,
        "status": "complete",
        "regatta": "demo",
        "course": "demo-course",
        "surfaces": {},
        "summary": {
            "repetitions": 1,
            "completed_runs": 1,
            "failed_runs": 0,
            "aggregate_logbooks": 1,
        },
        "runs": [
            {
                "index": 1,
                "logbook": "/tmp/logbook/runs/run-001",
                "status": "complete",
                "scorecard_present": True,
                "artifacts": {
                    "real_benchmark_eval": "/tmp/logbook/runs/run-001/real-benchmark-eval.json",
                    "benchmark_scorecard": "/tmp/logbook/runs/run-001/benchmark-scorecard.json",
                },
            }
        ],
        "artifacts": {
            "logbook": "/tmp/logbook",
            "real_benchmark_repetitions": "/tmp/logbook/real-benchmark-repetitions.json",
            "benchmark_aggregate": "/tmp/logbook/benchmark-aggregate.json",
            "benchmark_report_markdown": "/tmp/logbook/benchmark-report.md",
        },
        "next_steps": [],
    }


class RealBenchmarkRepetitionsSchemaTests(unittest.TestCase):
    def test_repetitions_documents_include_schema_version(self) -> None:
        validate_real_benchmark_repetitions_document(
            _valid_real_benchmark_repetitions_document()
        )

    def test_repetitions_rejects_unknown_status(self) -> None:
        document = _valid_real_benchmark_repetitions_document()
        document["status"] = "running"

        with self.assertRaisesRegex(ValueError, "status"):
            validate_real_benchmark_repetitions_document(document)

    def test_repetitions_requires_run_scorecard_presence_flag(self) -> None:
        document = _valid_real_benchmark_repetitions_document()
        del document["runs"][0]["scorecard_present"]

        with self.assertRaisesRegex(ValueError, "runs\\[0\\].scorecard_present"):
            validate_real_benchmark_repetitions_document(document)


def _valid_benchmark_aggregate_document() -> dict[str, Any]:
    return {
        "schema": BENCHMARK_AGGREGATE_SCHEMA,
        "regatta": "demo",
        "course": "demo-course",
        "run_count": 1,
        "logbooks": ["/tmp/logbook/runs/run-001"],
        "comparisons": [
            {
                "name": "comparison",
                "baseline": "baseline",
                "challenger": "challenger",
                "vessels": [
                    {
                        "name": "baseline",
                        "runs": 1,
                        "eligible_runs": 1,
                        "measured_runs": 1,
                        "submitted_instances": 2,
                        "resolved_instances": 1,
                        "resolution_rate": 0.5,
                        "usage_runs": 1,
                        "total_tokens": 1000,
                        "total_cost": 0.01,
                        "total_duration_seconds": 12.5,
                        "total_distinct_tool_uses": 4,
                    },
                    {
                        "name": "challenger",
                        "runs": 1,
                        "eligible_runs": 1,
                        "measured_runs": 1,
                        "submitted_instances": 2,
                        "resolved_instances": 2,
                        "resolution_rate": 1.0,
                        "usage_runs": 1,
                        "total_tokens": 900,
                        "total_cost": 0.009,
                        "total_duration_seconds": 11.0,
                        "total_distinct_tool_uses": 5,
                    },
                ],
                "runs": [],
                "delta": {"resolved_instances_delta": 1},
                "delta_statistics": {},
                "paired_statistics": {
                    "baseline_vessel": "baseline",
                    "challenger_vessel": "challenger",
                    "shared_task_attempts": 2,
                    "concordant_resolved": 1,
                    "concordant_unresolved": 0,
                    "discordant_baseline_only": 0,
                    "discordant_challenger_only": 1,
                    "discordant_by_task": [
                        {"task": "task-1", "baseline_only": 0, "challenger_only": 1}
                    ],
                    "grade": "insufficient-evidence",
                    "p_value": 1.0,
                    "min_significant_discordant": 6,
                },
            }
        ],
    }


class BenchmarkAggregateSchemaTests(unittest.TestCase):
    def test_aggregate_documents_include_schema_version(self) -> None:
        validate_benchmark_aggregate_document(_valid_benchmark_aggregate_document())

    def test_aggregate_accepts_pre_statistics_artifacts(self) -> None:
        document = _valid_benchmark_aggregate_document()
        del document["comparisons"][0]["paired_statistics"]
        del document["comparisons"][0]["delta_statistics"]

        validate_benchmark_aggregate_document(document)

    def test_aggregate_rejects_malformed_paired_statistics(self) -> None:
        document = _valid_benchmark_aggregate_document()
        del document["comparisons"][0]["paired_statistics"]["p_value"]

        with self.assertRaisesRegex(ValueError, "paired_statistics.*p_value"):
            validate_benchmark_aggregate_document(document)

    def test_aggregate_rejects_unknown_evidence_grade(self) -> None:
        document = _valid_benchmark_aggregate_document()
        document["comparisons"][0]["paired_statistics"]["grade"] = "definitely-better"

        with self.assertRaisesRegex(ValueError, "grade"):
            validate_benchmark_aggregate_document(document)

    def test_aggregate_requires_run_count_to_match_logbooks(self) -> None:
        document = _valid_benchmark_aggregate_document()
        document["run_count"] = 2

        with self.assertRaisesRegex(ValueError, "run_count"):
            validate_benchmark_aggregate_document(document)

    def test_aggregate_requires_vessel_usage_totals(self) -> None:
        document = _valid_benchmark_aggregate_document()
        del document["comparisons"][0]["vessels"][0]["total_tokens"]

        with self.assertRaisesRegex(ValueError, "total_tokens"):
            validate_benchmark_aggregate_document(document)

    def test_evidence_grades_match_statistics_module(self) -> None:
        from yacht.contracts.schemas import EVIDENCE_GRADES
        from yacht.reports.statistics import (
            GRADE_EVIDENCE,
            GRADE_INSUFFICIENT,
            GRADE_NOT_DISTINGUISHABLE,
        )

        self.assertEqual(
            EVIDENCE_GRADES,
            {GRADE_EVIDENCE, GRADE_INSUFFICIENT, GRADE_NOT_DISTINGUISHABLE},
        )


def _valid_terminal_bench_job_document() -> dict[str, Any]:
    return {
        "schema": TERMINAL_BENCH_JOB_SCHEMA,
        "dataset": {"name": "terminal-bench", "version": "2.0"},
        "tasks": ["task-1"],
        "agent": {
            "name": "claude-code",
            "import_path": "yacht_harbor_agents.agents:YachtClaudeCode",
            "version": "2.1.215",
            "model": "claude-sonnet-5",
            "env": {},
            "mcp_servers": [],
            "rigging_steps": [],
        },
        "launcher_image": "yacht/harbor-launcher:harbor-0.20.0",
        "secret_env": ["ANTHROPIC_API_KEY"],
        "vessel": "baseline",
    }


class TerminalBenchJobSchemaTests(unittest.TestCase):
    def test_job_documents_include_schema_version(self) -> None:
        validate_terminal_bench_job_document(_valid_terminal_bench_job_document())

    def test_job_accepts_custom_eval_dataset_digest(self) -> None:
        document = _valid_terminal_bench_job_document()
        document["dataset"] = {"path": "/tmp/evals", "digest": "sha256:abc123"}

        validate_terminal_bench_job_document(document)

    def test_job_requires_dataset_pin(self) -> None:
        document = _valid_terminal_bench_job_document()
        document["dataset"] = {"name": "terminal-bench"}

        with self.assertRaisesRegex(ValueError, "dataset"):
            validate_terminal_bench_job_document(document)

    def test_job_requires_agent_version(self) -> None:
        document = _valid_terminal_bench_job_document()
        del document["agent"]["version"]

        with self.assertRaisesRegex(ValueError, "agent.version"):
            validate_terminal_bench_job_document(document)

    def test_job_accepts_agent_episodes(self) -> None:
        document = _valid_terminal_bench_job_document()
        document["agent"]["episodes"] = {
            "task-1": {
                "max": 2,
                "verify_between": False,
                "instructions": ["Continue work on the project."],
            }
        }

        validate_terminal_bench_job_document(document)

    def test_job_rejects_episode_plan_max_below_two(self) -> None:
        document = _valid_terminal_bench_job_document()
        document["agent"]["episodes"] = {
            "task-1": {"max": 1, "verify_between": False, "instructions": []}
        }

        with self.assertRaisesRegex(ValueError, "episodes\\[task-1\\].max"):
            validate_terminal_bench_job_document(document)

    def test_job_rejects_episode_plan_instructions_length_mismatch(self) -> None:
        document = _valid_terminal_bench_job_document()
        document["agent"]["episodes"] = {
            "task-1": {
                "max": 3,
                "verify_between": False,
                "instructions": ["only one"],
            }
        }

        with self.assertRaisesRegex(ValueError, "episodes\\[task-1\\].instructions"):
            validate_terminal_bench_job_document(document)

    def test_job_rejects_episode_plan_for_task_not_in_job(self) -> None:
        document = _valid_terminal_bench_job_document()
        document["agent"]["episodes"] = {
            "not-a-real-task": {
                "max": 2,
                "verify_between": False,
                "instructions": ["x"],
            }
        }

        with self.assertRaisesRegex(ValueError, "does not match any task in the job"):
            validate_terminal_bench_job_document(document)

    def test_job_rejects_episode_plan_non_boolean_verify_between(self) -> None:
        document = _valid_terminal_bench_job_document()
        document["agent"]["episodes"] = {
            "task-1": {"max": 2, "verify_between": "yes", "instructions": ["x"]}
        }

        with self.assertRaisesRegex(ValueError, "episodes\\[task-1\\].verify_between"):
            validate_terminal_bench_job_document(document)


def _valid_course_grading_report_document() -> dict[str, Any]:
    return {
        "schema": SWE_BENCH_GRADING_SCHEMA,
        "regatta": "demo",
        "course": "demo-course",
        "adapter": "swe-bench",
        "dataset": "princeton-nlp/SWE-bench_Lite",
        "split": "dev",
        "status": "validated",
        "source_report_path": "/tmp/native-report.json",
        "candidate_patches_path": "/tmp/candidate-patches.jsonl",
        "submitted_instances": 2,
        "resolved_instances": 1,
        "resolution_rate": 0.5,
        "native_report": {"schema_version": 2},
        "vessel": "baseline",
    }


class CourseGradingReportSchemaTests(unittest.TestCase):
    def test_grading_report_documents_include_schema_version(self) -> None:
        validate_course_grading_report_document(_valid_course_grading_report_document())

    def test_grading_report_accepts_every_registered_course_schema(self) -> None:
        from yacht.courses.registry import (
            evaluator_adapter,
            supported_benchmark_adapter_kinds,
        )

        for kind in supported_benchmark_adapter_kinds():
            document = _valid_course_grading_report_document()
            document["schema"] = evaluator_adapter(kind).grading_schema

            validate_course_grading_report_document(document)

    def test_grading_report_rejects_unknown_schema(self) -> None:
        document = _valid_course_grading_report_document()
        document["schema"] = "yacht.aider-grading.v1"

        with self.assertRaisesRegex(ValueError, "schema"):
            validate_course_grading_report_document(document)

    def test_grading_report_requires_resolution_counts(self) -> None:
        document = _valid_course_grading_report_document()
        del document["resolved_instances"]

        with self.assertRaisesRegex(ValueError, "resolved_instances"):
            validate_course_grading_report_document(document)


class RealBenchmarkEvalSchemaTests(unittest.TestCase):
    def test_eval_summary_documents_include_schema_version(self) -> None:
        validate_real_benchmark_eval_document(
            {
                "schema": REAL_BENCHMARK_EVAL_SCHEMA,
                "status": "complete",
                "regatta": "demo",
                "course": "demo-course",
            }
        )

    def test_eval_summary_requires_schema_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "schema"):
            validate_real_benchmark_eval_document(
                {
                    "status": "complete",
                    "regatta": "demo",
                    "course": "demo-course",
                }
            )


def _valid_run_index_document() -> dict[str, Any]:
    return {
        "schema": RUN_INDEX_SCHEMA,
        "run_kind": "real-benchmark",
        "status": "complete",
        "updated_at": "2026-07-31T00:00:00Z",
        "config_path": "/tmp/regatta.toml",
        "logbook": "/tmp/logbook",
        "regatta": "demo",
        "course": "demo-course",
        "comparisons": [
            {
                "name": "comparison",
                "course": "demo-course",
                "vessels": ["baseline", "challenger"],
            }
        ],
        "artifacts": {
            "benchmark_scorecard": {
                "path": "/tmp/logbook/benchmark-scorecard.json",
                "present": False,
            }
        },
    }


def _valid_run_index_v2_document() -> dict[str, Any]:
    return {
        "schema": RUN_INDEX_V2_SCHEMA,
        "run_kind": "real-benchmark",
        "status": "running",
        "stage": "preflight",
        "started_at": "2026-08-19T00:00:00Z",
        "updated_at": "2026-08-19T00:01:00Z",
        "config_path": "/tmp/regatta.toml",
        "regatta": "demo",
        "course": "demo-course",
        "comparisons": [],
        "artifacts": {
            "benchmark_scorecard": {
                "path": "benchmark-scorecard.json",
                "present": False,
            }
        },
        "children": [
            {
                "path": "runs/run-1",
                "status": "complete",
            }
        ],
    }


class RunIndexSchemaTests(unittest.TestCase):
    def test_run_index_documents_include_schema_version(self) -> None:
        validate_run_index_document(_valid_run_index_document())

    def test_run_index_accepts_empty_comparisons_and_artifacts(self) -> None:
        document = _valid_run_index_document()
        document["comparisons"] = []
        document["artifacts"] = {}

        validate_run_index_document(document)

    def test_run_index_requires_status(self) -> None:
        document = _valid_run_index_document()
        del document["status"]

        with self.assertRaisesRegex(ValueError, "run index.*status"):
            validate_run_index_document(document)

    def test_run_index_rejects_unknown_schema(self) -> None:
        document = _valid_run_index_document()
        document["schema"] = "yacht.run-index.v3"

        with self.assertRaisesRegex(ValueError, "schema"):
            validate_run_index_document(document)

    def test_run_index_rejects_unknown_run_kind(self) -> None:
        document = _valid_run_index_document()
        document["run_kind"] = "dry-run"

        with self.assertRaisesRegex(ValueError, "run_kind"):
            validate_run_index_document(document)

    def test_run_index_rejects_comparison_without_vessels(self) -> None:
        document = _valid_run_index_document()
        document["comparisons"] = [{"name": "comparison", "course": "demo-course"}]

        with self.assertRaisesRegex(ValueError, "comparisons\\[0\\].*vessels"):
            validate_run_index_document(document)

    def test_run_index_rejects_artifact_entry_without_presence(self) -> None:
        document = _valid_run_index_document()
        document["artifacts"]["benchmark_scorecard"] = {"path": "x.json"}

        with self.assertRaisesRegex(
            ValueError,
            "artifacts.benchmark_scorecard.*present",
        ):
            validate_run_index_document(document)

    def test_run_index_v2_accepts_relative_references(self) -> None:
        validate_run_index_document(_valid_run_index_v2_document())

    def test_run_index_v2_requires_terminal_timestamp_when_complete(self) -> None:
        document = _valid_run_index_v2_document()
        document["status"] = "complete"
        document["stage"] = "complete"

        with self.assertRaisesRegex(ValueError, "terminal_at"):
            validate_run_index_document(document)

    def test_run_index_v2_rejects_terminal_timestamp_while_running(self) -> None:
        document = _valid_run_index_v2_document()
        document["terminal_at"] = "2026-08-19T00:02:00Z"

        with self.assertRaisesRegex(ValueError, "terminal_at"):
            validate_run_index_document(document)

    def test_run_index_v2_rejects_traversal_reference(self) -> None:
        document = _valid_run_index_v2_document()
        document["artifacts"]["benchmark_scorecard"]["path"] = "../scorecard.json"

        with self.assertRaisesRegex(ValueError, "path"):
            validate_run_index_document(document)


if __name__ == "__main__":
    unittest.main()
