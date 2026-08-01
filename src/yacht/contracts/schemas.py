from __future__ import annotations

import re
from typing import Any

from yacht.courses.registry import evaluator_adapter
from yacht.courses.registry import supported_benchmark_adapter_kinds
from yacht.courses.registry import supported_course_adapter_harnesses
from yacht.harnesses.mcp_config import supported_mcp_install_provider
from yacht.runtimes.tool_capabilities import BUILT_IN_TOOL_CAPABILITIES


REGATTA_SCHEMA = "yacht.regatta.v1"
WAKE_SCHEMA = "yacht.wake.v1"
SCORECARD_SCHEMA = "yacht.scorecard.v1"
PREFLIGHT_SCHEMA = "yacht.preflight.v1"
PREFLIGHT_SUMMARY_SCHEMA = "yacht.preflight-summary.v1"
PREFLIGHT_EVIDENCE_REPORT_SCHEMA = "yacht.preflight-evidence-report.v1"
COURSE_HANDOFF_SCHEMA = "yacht.course-handoff.v1"
BENCHMARK_SCORECARD_SCHEMA = "yacht.benchmark-scorecard.v1"
BENCHMARK_EXECUTION_PLAN_SCHEMA = "yacht.benchmark-execution-plan.v1"
BENCHMARK_LAUNCHER_HANDOFF_SCHEMA = "yacht.benchmark-launcher-handoff.v1"
BENCHMARK_LAUNCH_RESULT_SCHEMA = "yacht.benchmark-launch-result.v1"
BENCHMARK_READINESS_SUMMARY_SCHEMA = "yacht.benchmark-readiness-summary.v1"
RUNTIME_INSTANCES_SCHEMA = "yacht.runtime-instances.v1"
TASK_ATTEMPT_SCHEMA = "yacht.task-attempt.v1"
TASK_ATTEMPT_SCORECARD_SCHEMA = "yacht.task-attempt-scorecard.v1"
SMOKE_READINESS_REPORT_SCHEMA = "yacht.smoke-readiness-report.v1"
REAL_SMOKE_RUNBOOK_SCHEMA = "yacht.real-smoke-runbook.v1"
REAL_BENCHMARK_RUNBOOK_SCHEMA = "yacht.real-benchmark-runbook.v1"
HARNESS_EVIDENCE_SCHEMA = "yacht.harness-evidence.v1"
RUN_INDEX_SCHEMA = "yacht.run-index.v1"
BENCHMARK_GRADING_COLLECTION_SCHEMA = "yacht.benchmark-grading-collection.v1"
REAL_BENCHMARK_REPETITIONS_SCHEMA = "yacht.real-benchmark-repetitions.v1"
REAL_BENCHMARK_EVAL_SCHEMA = "yacht.real-benchmark-eval.v1"
BENCHMARK_AGGREGATE_SCHEMA = "yacht.benchmark-aggregate.v1"
TERMINAL_BENCH_JOB_SCHEMA = "yacht.terminal-bench-job.v1"
SWE_BENCH_GRADING_SCHEMA = "yacht.swe-bench-grading.v1"
TERMINAL_BENCH_GRADING_SCHEMA = "yacht.terminal-bench-grading.v1"
LIVECODEBENCH_GRADING_SCHEMA = "yacht.livecodebench-grading.v1"
# Derived from the registry, like COURSE_ADAPTER_KINDS: courses that
# reuse another course's grading writer under their own schema name
# (aider-polyglot, custom-eval) declare it only there, and a hand-kept
# list silently missed them.
COURSE_GRADING_SCHEMAS = {
    evaluator_adapter(kind).grading_schema
    for kind in supported_benchmark_adapter_kinds()
}

# Kept in sync with yacht.harnesses.registry.supported_harness_names()
# by a test; imported directly it would create an import cycle.
BUILT_IN_HARNESS_NAMES = {"claude-code", "local-smoke", "pi"}
HARNESS_PROMPT_MODES = {"argument", "stdin"}
HARNESS_EVIDENCE_SOURCES = {"stdout", "file"}
METRICS_USAGE_SOURCES = {"reported", "estimated", "unreported"}
# Cost is never estimated: a harness either reported it or it is absent.
COST_SOURCES = {"reported", "unreported"}
EVALUATOR_RELATIONSHIPS = {
    "first_party",
    "third_party",
    "collaborative",
    "other",
}
# Pinned external contract (ADR 0020): a schema bump is a deliberate
# change with a visible diff, never silent divergence.
EVERY_EVAL_EVER_SCHEMA_VERSION = "0.2.2"
EVERY_EVAL_EVER_INSTANCE_SCHEMA_VERSION = "instance_level_eval_0.2.2"
EVERY_EVAL_EVER_SOURCE_TYPES = {"documentation", "evaluation_run"}
EVERY_EVAL_EVER_SCORE_TYPES = {"binary", "continuous", "levels"}
EVERY_EVAL_EVER_INTERACTION_TYPES = {"single_turn", "multi_turn", "agentic"}
EVERY_EVAL_EVER_DATASET_SOURCE_TYPES = {"url", "hf_dataset", "other"}

PREFLIGHT_FAILURE_POLICIES = {"abort-group", "skip-vessel", "abort-regatta", "warn"}
COURSE_ADAPTER_KINDS = set(supported_benchmark_adapter_kinds())
COURSE_ADAPTER_HARNESSES = set(supported_course_adapter_harnesses())
RIGGING_INSTALL_METHODS = {
    "agent-extension",
    "mcp-server",
    "package",
    "binary",
    "container-image",
    "config-file",
    "preinstalled",
    "custom-command",
}
PREFLIGHT_CHECK_KINDS = {
    "agent-prompt",
    "artifact",
    "command",
    "env",
    "install-only",
    "mcp-server",
    "path-isolation",
    "runtime-capability",
    "tool-call",
}
PREFLIGHT_STATUSES = {"passed", "failed", "error", "skipped"}
PREFLIGHT_SUMMARY_STATUSES = {"passed", "failed", "invalid"}
PREFLIGHT_SUMMARY_CHECK_STATUSES = PREFLIGHT_STATUSES | {"omitted"}
PREFLIGHT_EVIDENCE_REPORT_STATUSES = {"blocked", "ready"}
PREFLIGHT_EVIDENCE_REPORT_VESSEL_STATUSES = {
    "eligible",
    "missing-preflight",
    "preflight-error",
    "preflight-failed",
    "preflight-invalid",
    "preflight-skipped",
    "unsupported-rigging-capability",
}
BENCHMARK_SCORECARD_STATUSES = {"complete", "partial", "empty"}
BENCHMARK_SCORECARD_VESSEL_STATUSES = {"measured", "missing", "recorded"}
BENCHMARK_SCORECARD_SUMMARY_KEYS = (
    "total_vessels",
    "eligible_vessels",
    "blocked_vessels",
    "measured_vessels",
    "missing_result_vessels",
)
BENCHMARK_EXECUTION_PLAN_STATUSES = {
    "blocked",
    "complete",
    "mixed",
    "missing-inputs",
    "ready-for-grading",
}
BENCHMARK_EXECUTION_PLAN_VESSEL_STATUSES = {
    "graded",
    "missing-candidate-patches",
    "missing-preflight",
    "missing-runtime-snapshot",
    "preflight-failed",
    "ready-for-grading",
}
BENCHMARK_READINESS_BLOCKED_VESSEL_STATUSES = (
    BENCHMARK_EXECUTION_PLAN_VESSEL_STATUSES - {"graded", "ready-for-grading"}
)
BENCHMARK_LAUNCHER_HANDOFF_STATUSES = {
    "blocked",
    "complete",
    "mixed",
    "missing-inputs",
    "ready-to-launch",
}
BENCHMARK_LAUNCHER_HANDOFF_VESSEL_STATUSES = {
    "already-graded",
    "missing-candidate-patches",
    "missing-preflight",
    "missing-runtime-snapshot",
    "preflight-failed",
    "ready-to-launch",
}
BENCHMARK_LAUNCH_RESULT_STATUSES = {"blocked", "complete", "failed", "partial"}
RUN_INDEX_RUN_KINDS = {"real-benchmark", "real-smoke"}
BENCHMARK_GRADING_COLLECTION_STATUSES = {"blocked", "complete", "partial"}
BENCHMARK_GRADING_COLLECTION_VESSEL_STATUSES = {
    "collected",
    "invalid-native-report",
    "missing-native-report",
    "skipped",
}
REAL_BENCHMARK_REPETITIONS_STATUSES = {"blocked", "complete", "partial"}
# Kept in sync with yacht.reports.statistics GRADE_* constants by a test;
# imported directly the contracts module would depend on the reports layer.
EVIDENCE_GRADES = {
    "evidence-of-difference",
    "insufficient-evidence",
    "not-distinguishable",
}
BENCHMARK_LAUNCH_RESULT_VESSEL_STATUSES = {"completed", "failed", "skipped"}
TASK_ATTEMPT_STATUSES = {"completed", "failed"}
TASK_ATTEMPT_SCORECARD_STATUSES = {"complete", "partial"}
TASK_ATTEMPT_SCORECARD_VESSEL_STATUSES = {"measured", "failed"}
SMOKE_READINESS_REPORT_STATUSES = {"ready", "blocked"}
SMOKE_READINESS_REPORT_VESSEL_STATUSES = {
    "ready",
    "missing-preflight",
    "preflight-failed",
    "preflight-invalid",
    "missing-agent-prompt-evidence",
    "missing-expected-tool-calls",
    "task-attempt-failed",
    "task-attempt-invalid",
}


class SchemaValidationError(ValueError):
    """Raised when a YACHT document does not match its contract."""


def validate_regatta_document(document: dict[str, Any]) -> None:
    _require_object(document, "regatta document")
    _require_keys(document, ("regatta", "course", "vessels"), "regatta document")
    _validate_preflight_config(document)
    secrets = _validate_secret_references(document)
    _validate_harness_declarations(document)
    _validate_declared_evidence_backends(document)
    runtime_names = _validate_runtime_recipes(document, secrets)
    tool_names = _validate_tool_capabilities(document)
    rigging_names = _validate_rigging_recipes(document, secrets, tool_names)

    regatta = _require_object(document["regatta"], "regatta")
    _require_non_empty_string(regatta.get("name"), "regatta.name")

    course = _require_object(document["course"], "course")
    _require_non_empty_string(course.get("name"), "course.name")
    course_name = course["name"]
    _validate_course_adapter(course)
    adapter = course.get("adapter")
    adapter_selects_instances = _course_adapter_selects_instances(adapter)
    if "tasks" in course and "task_file" in course:
        raise SchemaValidationError("course must not define both tasks and task_file")
    if "tasks" in course and "task_files" in course:
        raise SchemaValidationError("course must not define both tasks and task_files")
    if "task_file" in course and "task_files" in course:
        raise SchemaValidationError(
            "course must not define both task_file and task_files"
        )
    if "task_file" in course:
        _require_non_empty_string(course.get("task_file"), "course.task_file")
    if "task_files" in course:
        task_files = _require_list(course.get("task_files"), "course.task_files")
        if not task_files:
            raise SchemaValidationError(
                "course.task_files must contain at least one file"
            )
        for index, task_file in enumerate(task_files):
            _require_non_empty_string(task_file, f"course.task_files[{index}]")
    if (
        "tasks" not in course
        and "task_file" not in course
        and "task_files" not in course
        and not adapter_selects_instances
    ):
        raise SchemaValidationError(
            "course.tasks, course.task_file, or course.task_files must define at "
            "least one task unless course.adapter selects benchmark tasks"
        )
    tasks = _require_list(course.get("tasks", []), "course.tasks")
    if (
        not tasks
        and "task_file" not in course
        and "task_files" not in course
        and not adapter_selects_instances
    ):
        raise SchemaValidationError("course.tasks must contain at least one task")
    adapter_instance_ids = _course_adapter_instance_ids(adapter)
    task_ids = set()
    for index, task_value in enumerate(tasks):
        task = _require_object(task_value, f"course.tasks[{index}]")
        _require_non_empty_string(task.get("id"), f"course.tasks[{index}].id")
        if task["id"] in task_ids:
            raise SchemaValidationError(f"course.tasks[{index}].id is duplicated")
        task_ids.add(task["id"])
        _require_non_empty_string(task.get("title"), f"course.tasks[{index}].title")
        difficulty = task.get("difficulty", 1)
        if not isinstance(difficulty, int) or difficulty < 1:
            raise SchemaValidationError(
                f"course.tasks[{index}].difficulty must be an integer >= 1"
            )
        for field in ("repo", "repo_url", "base_commit", "problem_statement"):
            if field in task:
                _require_non_empty_string(
                    task.get(field),
                    f"course.tasks[{index}].{field}",
                )
        if "expect_response" in task:
            _validate_expect_response(
                task["expect_response"],
                f"course.tasks[{index}].expect_response",
            )
        if "expect_tool_calls" in task:
            _validate_expect_tool_calls(
                task["expect_tool_calls"],
                f"course.tasks[{index}].expect_tool_calls",
            )
    if adapter_instance_ids:
        extra_task_ids = task_ids - set(adapter_instance_ids)
        if extra_task_ids:
            raise SchemaValidationError(
                "course.tasks contains IDs not selected by course.adapter.instance_ids"
            )

    vessels = _require_list(document["vessels"], "vessels")
    if not vessels:
        raise SchemaValidationError("vessels must contain at least one vessel")
    adapter_kind = adapter.get("kind") if isinstance(adapter, dict) else None
    native_rollout = _adapter_native_rollout(adapter_kind)
    runtimes_table = _optional_named_table(document, "runtimes")
    vessel_names = set()
    for index, vessel_value in enumerate(vessels):
        vessel = _require_object(vessel_value, f"vessels[{index}]")
        _require_non_empty_string(vessel.get("name"), f"vessels[{index}].name")
        vessel_names.add(vessel["name"])
        _require_non_empty_string(vessel.get("model"), f"vessels[{index}].model")
        runtime = vessel.get("runtime")
        if runtime is not None:
            _require_non_empty_string(runtime, f"vessels[{index}].runtime")
            if runtime not in runtime_names:
                raise SchemaValidationError(
                    f"vessels[{index}].runtime references undefined runtime {runtime}"
                )
            backend = runtimes_table.get(runtime, {}).get("backend")
            if native_rollout and backend != "harbor":
                raise SchemaValidationError(
                    f"vessels[{index}].runtime {runtime} must use the harbor "
                    f"backend for the {adapter_kind} course"
                )
            if not native_rollout and backend == "harbor":
                raise SchemaValidationError(
                    f"vessels[{index}].runtime {runtime} uses the harbor "
                    "backend, which requires a native-rollout course"
                )
        rigging = vessel.get("rigging", [])
        if not isinstance(rigging, list) or not all(
            isinstance(item, str) for item in rigging
        ):
            raise SchemaValidationError(
                f"vessels[{index}].rigging must be a list of strings"
            )
        if rigging_names:
            for rigging_name in rigging:
                if rigging_name not in rigging_names:
                    raise SchemaValidationError(
                        f"vessels[{index}].rigging references undefined rigging "
                        f"{rigging_name}"
                    )
    _validate_comparisons(document, course_name, vessel_names)
    if "export" in document:
        _validate_export_attribution(document["export"], "export")


def validate_every_eval_ever_document(document: dict[str, Any]) -> None:
    """Validate an export against the pinned Every Eval Ever schema.

    Hand-rolled in the house style so the export carries no runtime
    dependency on the external project; the pinned version constant is
    what ties this to their contract.
    """
    _require_object(document, "every eval ever")
    _require_keys(
        document,
        (
            "schema_version",
            "evaluation_id",
            "retrieved_timestamp",
            "source_metadata",
            "eval_library",
            "model_info",
            "evaluation_results",
        ),
        "every eval ever",
    )
    if document["schema_version"] != EVERY_EVAL_EVER_SCHEMA_VERSION:
        raise SchemaValidationError(
            "schema_version must be " + EVERY_EVAL_EVER_SCHEMA_VERSION
        )
    for key in ("evaluation_id", "retrieved_timestamp"):
        _require_non_empty_string(document[key], key)
    if "evaluation_timestamp" in document:
        _require_non_empty_string(
            document["evaluation_timestamp"],
            "evaluation_timestamp",
        )

    source_metadata = _require_object(document["source_metadata"], "source_metadata")
    _require_keys(
        source_metadata,
        ("source_type", "source_organization_name", "evaluator_relationship"),
        "source_metadata",
    )
    _require_allowed_value(
        source_metadata["source_type"],
        EVERY_EVAL_EVER_SOURCE_TYPES,
        "source_metadata.source_type",
    )
    _require_non_empty_string(
        source_metadata["source_organization_name"],
        "source_metadata.source_organization_name",
    )
    _require_allowed_value(
        source_metadata["evaluator_relationship"],
        EVALUATOR_RELATIONSHIPS,
        "source_metadata.evaluator_relationship",
    )

    eval_library = _require_object(document["eval_library"], "eval_library")
    _require_keys(eval_library, ("name", "version"), "eval_library")
    for key in ("name", "version"):
        _require_non_empty_string(eval_library[key], f"eval_library.{key}")

    model_info = _require_object(document["model_info"], "model_info")
    _require_keys(model_info, ("name", "id"), "model_info")
    for key in ("name", "id"):
        _require_non_empty_string(model_info[key], f"model_info.{key}")
    if "additional_details" in model_info:
        _require_string_mapping(
            model_info["additional_details"],
            "model_info.additional_details",
        )

    results = _require_list(document["evaluation_results"], "evaluation_results")
    if not results:
        raise SchemaValidationError(
            "evaluation_results must contain at least one result"
        )
    for index, result_value in enumerate(results):
        _validate_every_eval_ever_result(result_value, f"evaluation_results[{index}]")
    if "detailed_evaluation_results" in document:
        _validate_every_eval_ever_detailed(
            document["detailed_evaluation_results"],
            "detailed_evaluation_results",
        )


def _validate_every_eval_ever_result(value: Any, path: str) -> None:
    result = _require_object(value, path)
    _require_keys(
        result,
        ("evaluation_name", "source_data", "metric_config", "score_details"),
        path,
    )
    _require_non_empty_string(result["evaluation_name"], f"{path}.evaluation_name")

    source_data = _require_object(result["source_data"], f"{path}.source_data")
    _require_keys(source_data, ("dataset_name", "source_type"), f"{path}.source_data")
    _require_non_empty_string(
        source_data["dataset_name"],
        f"{path}.source_data.dataset_name",
    )
    _require_allowed_value(
        source_data["source_type"],
        EVERY_EVAL_EVER_DATASET_SOURCE_TYPES,
        f"{path}.source_data.source_type",
    )
    if source_data["source_type"] == "url":
        _require_non_empty_string(source_data.get("url"), f"{path}.source_data.url")
    if "additional_details" in source_data:
        _require_string_mapping(
            source_data["additional_details"],
            f"{path}.source_data.additional_details",
        )

    metric_config = _require_object(result["metric_config"], f"{path}.metric_config")
    _require_keys(metric_config, ("lower_is_better",), f"{path}.metric_config")
    if not isinstance(metric_config["lower_is_better"], bool):
        raise SchemaValidationError(
            f"{path}.metric_config.lower_is_better must be a boolean"
        )
    if "score_type" in metric_config:
        _require_allowed_value(
            metric_config["score_type"],
            EVERY_EVAL_EVER_SCORE_TYPES,
            f"{path}.metric_config.score_type",
        )

    score_details = _require_object(result["score_details"], f"{path}.score_details")
    _require_keys(score_details, ("score",), f"{path}.score_details")
    score = score_details["score"]
    if not isinstance(score, int | float) or isinstance(score, bool):
        raise SchemaValidationError(f"{path}.score_details.score must be a number")
    if "details" in score_details:
        _require_string_mapping(
            score_details["details"],
            f"{path}.score_details.details",
        )
    if "uncertainty" in score_details:
        _validate_every_eval_ever_uncertainty(
            score_details["uncertainty"],
            f"{path}.score_details.uncertainty",
        )
    if "additional_details" in result:
        _require_string_mapping(
            result["additional_details"],
            f"{path}.additional_details",
        )


def _validate_every_eval_ever_uncertainty(value: Any, path: str) -> None:
    uncertainty = _require_object(value, path)
    interval = uncertainty.get("confidence_interval")
    if interval is not None:
        interval_object = _require_object(interval, f"{path}.confidence_interval")
        for key in ("lower", "upper"):
            bound = interval_object.get(key)
            if not isinstance(bound, int | float) or isinstance(bound, bool):
                raise SchemaValidationError(
                    f"{path}.confidence_interval.{key} must be a number"
                )
        level = interval_object.get("confidence_level")
        if level is not None and (
            not isinstance(level, int | float)
            or isinstance(level, bool)
            or not 0.0 <= float(level) <= 1.0
        ):
            raise SchemaValidationError(
                f"{path}.confidence_interval.confidence_level must be between 0 and 1"
            )
    standard_error = uncertainty.get("standard_error")
    if standard_error is not None:
        error_object = _require_object(standard_error, f"{path}.standard_error")
        _require_keys(error_object, ("value",), f"{path}.standard_error")


def _validate_every_eval_ever_detailed(value: Any, path: str) -> None:
    detailed = _require_object(value, path)
    for key in ("format", "file_path"):
        if key in detailed:
            _require_non_empty_string(detailed[key], f"{path}.{key}")
    if "total_rows" in detailed:
        _require_non_negative_int(detailed["total_rows"], f"{path}.total_rows")
    if "checksum" in detailed:
        _require_non_empty_string(detailed["checksum"], f"{path}.checksum")


def validate_every_eval_ever_instance_row(row: dict[str, Any]) -> None:
    _require_object(row, "every eval ever instance")
    _require_keys(
        row,
        (
            "schema_version",
            "evaluation_id",
            "model_id",
            "evaluation_name",
            "sample_id",
            "interaction_type",
            "input",
            "answer_attribution",
            "evaluation",
        ),
        "every eval ever instance",
    )
    if row["schema_version"] != EVERY_EVAL_EVER_INSTANCE_SCHEMA_VERSION:
        raise SchemaValidationError(
            "schema_version must be " + EVERY_EVAL_EVER_INSTANCE_SCHEMA_VERSION
        )
    for key in ("evaluation_id", "model_id", "evaluation_name", "sample_id"):
        _require_non_empty_string(row[key], key)
    _require_allowed_value(
        row["interaction_type"],
        EVERY_EVAL_EVER_INTERACTION_TYPES,
        "interaction_type",
    )
    input_object = _require_object(row["input"], "input")
    _require_keys(input_object, ("raw", "reference"), "input")
    if not isinstance(input_object["raw"], str):
        raise SchemaValidationError("input.raw must be a string")
    _require_string_list(input_object["reference"], "input.reference")

    attributions = _require_list(row["answer_attribution"], "answer_attribution")
    if not attributions:
        raise SchemaValidationError(
            "answer_attribution must contain at least one entry"
        )
    for index, attribution_value in enumerate(attributions):
        attribution_path = f"answer_attribution[{index}]"
        attribution = _require_object(attribution_value, attribution_path)
        _require_keys(
            attribution,
            (
                "turn_idx",
                "source",
                "extracted_value",
                "extraction_method",
                "is_terminal",
            ),
            attribution_path,
        )
        _require_non_negative_int(
            attribution["turn_idx"],
            f"{attribution_path}.turn_idx",
        )
        for key in ("source", "extracted_value", "extraction_method"):
            _require_non_empty_string(
                attribution[key],
                f"{attribution_path}.{key}",
            )
        if not isinstance(attribution["is_terminal"], bool):
            raise SchemaValidationError(
                f"{attribution_path}.is_terminal must be a boolean"
            )

    # Agentic and multi-turn rows carry a transcript instead of a single
    # output; single-turn rows are the other way round.
    if row["interaction_type"] in {"agentic", "multi_turn"}:
        messages = _require_list(row.get("messages"), "messages")
        if not messages:
            raise SchemaValidationError(
                "messages must contain at least one turn for "
                f"{row['interaction_type']} rows"
            )
        for index, message_value in enumerate(messages):
            message_path = f"messages[{index}]"
            message = _require_object(message_value, message_path)
            _require_keys(message, ("turn_idx", "role"), message_path)
            _require_non_negative_int(
                message["turn_idx"],
                f"{message_path}.turn_idx",
            )
            _require_non_empty_string(message["role"], f"{message_path}.role")
            content = message.get("content")
            if content is not None and not isinstance(content, str):
                raise SchemaValidationError(
                    f"{message_path}.content must be a string or null"
                )
        if row.get("output") is not None:
            raise SchemaValidationError(
                f"output must be null for {row['interaction_type']} rows"
            )
    elif row.get("output") is None:
        raise SchemaValidationError("output is required for single_turn rows")

    evaluation = _require_object(row["evaluation"], "evaluation")
    _require_keys(evaluation, ("score", "is_correct"), "evaluation")
    if not isinstance(evaluation["score"], int | float) or isinstance(
        evaluation["score"], bool
    ):
        raise SchemaValidationError("evaluation.score must be a number")
    if not isinstance(evaluation["is_correct"], bool):
        raise SchemaValidationError("evaluation.is_correct must be a boolean")
    if "tool_calls_count" in evaluation:
        _require_non_negative_int(
            evaluation["tool_calls_count"],
            "evaluation.tool_calls_count",
        )
    if "token_usage" in row:
        usage = _require_object(row["token_usage"], "token_usage")
        _require_keys(
            usage,
            ("input_tokens", "output_tokens", "total_tokens"),
            "token_usage",
        )
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            _require_non_negative_int(usage[key], f"token_usage.{key}")


def _validate_export_attribution(value: Any, path: str) -> None:
    export = _require_object(value, path)
    _require_keys(
        export,
        ("source_organization_name", "evaluator_relationship"),
        path,
    )
    _require_non_empty_string(
        export.get("source_organization_name"),
        f"{path}.source_organization_name",
    )
    _require_allowed_value(
        export.get("evaluator_relationship"),
        EVALUATOR_RELATIONSHIPS,
        f"{path}.evaluator_relationship",
    )
    for key in ("source_organization_url", "source_name"):
        if key in export:
            _require_non_empty_string(export.get(key), f"{path}.{key}")


def validate_wake_document(document: dict[str, Any]) -> None:
    _require_object(document, "wake")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "vessel",
            "model",
            "rigging",
            "task_id",
            "task_title",
            "passed",
            "metrics",
        ),
        "wake",
    )
    _require_schema(document, WAKE_SCHEMA, "wake")
    for key in ("regatta", "course", "vessel", "model", "task_id", "task_title"):
        _require_non_empty_string(document[key], key)
    _require_string_list(document["rigging"], "rigging")
    if not isinstance(document["passed"], bool):
        raise SchemaValidationError("passed must be a boolean")

    metrics = _require_object(document["metrics"], "metrics")
    if not isinstance(metrics.get("tokens"), int) or metrics["tokens"] < 0:
        raise SchemaValidationError("metrics.tokens must be an integer >= 0")
    if (
        not isinstance(metrics.get("duration_seconds"), int | float)
        or metrics["duration_seconds"] < 0
    ):
        raise SchemaValidationError("metrics.duration_seconds must be a number >= 0")
    if "usage_source" in metrics:
        _require_allowed_value(
            metrics.get("usage_source"),
            METRICS_USAGE_SOURCES,
            "metrics.usage_source",
        )


def validate_scorecard_document(document: dict[str, Any]) -> None:
    _require_object(document, "scorecard")
    _require_keys(document, ("schema", "regatta", "course", "vessels"), "scorecard")
    _require_schema(document, SCORECARD_SCHEMA, "scorecard")
    _require_non_empty_string(document["regatta"], "regatta")
    _require_non_empty_string(document["course"], "course")

    vessels = _require_list(document["vessels"], "vessels")
    if not vessels:
        raise SchemaValidationError("vessels must contain at least one vessel")
    for index, vessel_value in enumerate(vessels):
        vessel = _require_object(vessel_value, f"vessels[{index}]")
        _require_non_empty_string(vessel.get("name"), f"vessels[{index}].name")
        _require_non_empty_string(vessel.get("model"), f"vessels[{index}].model")
        _require_string_list(vessel.get("rigging"), f"vessels[{index}].rigging")
        for key in ("tasks_total", "tasks_passed", "total_tokens"):
            value = vessel.get(key)
            if not isinstance(value, int) or value < 0:
                raise SchemaValidationError(
                    f"vessels[{index}].{key} must be an integer >= 0"
                )
        for key in ("success_rate", "total_duration_seconds"):
            value = vessel.get(key)
            if not isinstance(value, int | float) or value < 0:
                raise SchemaValidationError(
                    f"vessels[{index}].{key} must be a number >= 0"
                )


def validate_preflight_document(document: dict[str, Any]) -> None:
    _require_object(document, "preflight")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "vessel",
            "runtime",
            "workspace_path",
            "temp_home",
            "command_prefix",
            "cleanup_paths",
            "status",
            "failure_policy",
            "checks",
            "secret_refs",
        ),
        "preflight",
    )
    _require_schema(document, PREFLIGHT_SCHEMA, "preflight")
    for key in (
        "regatta",
        "vessel",
        "runtime",
        "workspace_path",
        "temp_home",
        "failure_policy",
    ):
        _require_non_empty_string(document[key], key)
    _require_string_list(document["command_prefix"], "command_prefix")
    _require_string_list(document["cleanup_paths"], "cleanup_paths")
    if "runtime_setup" in document:
        _validate_runtime_setup(document["runtime_setup"], "runtime_setup")
    _require_allowed_value(
        document["status"],
        PREFLIGHT_STATUSES,
        "status",
    )
    _require_allowed_value(
        document["failure_policy"],
        PREFLIGHT_FAILURE_POLICIES,
        "failure_policy",
    )
    for key in ("comparison",):
        if key in document:
            _require_non_empty_string(document[key], key)

    secret_refs = _require_list(document["secret_refs"], "secret_refs")
    for index, secret_ref_value in enumerate(secret_refs):
        secret_ref = _require_object(secret_ref_value, f"secret_refs[{index}]")
        for key in ("name", "source", "ref"):
            _require_non_empty_string(
                secret_ref.get(key), f"secret_refs[{index}].{key}"
            )
        if secret_ref.get("redacted") is not True:
            raise SchemaValidationError(f"secret_refs[{index}].redacted must be true")

    checks = _require_list(document["checks"], "checks")
    if not checks:
        raise SchemaValidationError("checks must contain at least one check")
    for index, check_value in enumerate(checks):
        check = _require_object(check_value, f"checks[{index}]")
        _require_keys(
            check,
            (
                "name",
                "kind",
                "origin",
                "origin_name",
                "required",
                "status",
                "evidence",
            ),
            f"checks[{index}]",
        )
        _require_non_empty_string(check.get("name"), f"checks[{index}].name")
        _require_allowed_value(
            check.get("origin"),
            {"runtime", "rigging"},
            f"checks[{index}].origin",
        )
        _require_non_empty_string(
            check.get("origin_name"),
            f"checks[{index}].origin_name",
        )
        _require_allowed_value(
            check.get("kind"),
            PREFLIGHT_CHECK_KINDS,
            f"checks[{index}].kind",
        )
        _require_allowed_value(
            check.get("status"),
            PREFLIGHT_STATUSES,
            f"checks[{index}].status",
        )
        if not isinstance(check.get("required"), bool):
            raise SchemaValidationError(f"checks[{index}].required must be a boolean")
        evidence = _require_object(check["evidence"], f"checks[{index}].evidence")
        _require_string_list(
            evidence.get("tool_calls", []),
            f"checks[{index}].evidence.tool_calls",
        )
        _require_string_list(
            evidence.get("expected_tool_calls", []),
            f"checks[{index}].evidence.expected_tool_calls",
        )


def _validate_runtime_setup(value: Any, path: str) -> None:
    setup_results = _require_list(value, path)
    for index, setup_value in enumerate(setup_results):
        setup_path = f"{path}[{index}]"
        setup = _require_object(setup_value, setup_path)
        _require_keys(
            setup,
            (
                "origin",
                "origin_name",
                "action",
                "target",
                "argv",
                "exit_code",
                "stdout",
                "stderr",
            ),
            setup_path,
        )
        _require_allowed_value(setup["origin"], {"rigging"}, f"{setup_path}.origin")
        for key in ("origin_name", "action", "target", "stdout", "stderr"):
            _require_string(setup.get(key), f"{setup_path}.{key}")
        _require_string_list(setup["argv"], f"{setup_path}.argv")
        if not isinstance(setup.get("exit_code"), int):
            raise SchemaValidationError(f"{setup_path}.exit_code must be an integer")


def validate_preflight_summary_document(document: dict[str, Any]) -> None:
    _require_object(document, "preflight summary")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "status",
            "preflight_failure_policy",
            "comparisons",
        ),
        "preflight summary",
    )
    _require_schema(document, PREFLIGHT_SUMMARY_SCHEMA, "preflight summary")
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], key)
    _require_allowed_value(
        document["status"],
        PREFLIGHT_SUMMARY_STATUSES,
        "status",
    )
    _require_allowed_value(
        document["preflight_failure_policy"],
        PREFLIGHT_FAILURE_POLICIES,
        "preflight_failure_policy",
    )

    comparisons = _require_list(document["comparisons"], "comparisons")
    if not comparisons:
        raise SchemaValidationError("comparisons must contain at least one comparison")
    for comparison_index, comparison_value in enumerate(comparisons):
        comparison_path = f"comparisons[{comparison_index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(comparison, ("name", "status", "vessels"), comparison_path)
        _require_non_empty_string(comparison.get("name"), f"{comparison_path}.name")
        _require_allowed_value(
            comparison.get("status"),
            PREFLIGHT_SUMMARY_STATUSES,
            f"{comparison_path}.status",
        )
        vessels = _require_list(comparison["vessels"], f"{comparison_path}.vessels")
        if not vessels:
            raise SchemaValidationError(
                f"{comparison_path}.vessels must contain at least one vessel"
            )
        for vessel_index, vessel_value in enumerate(vessels):
            vessel_path = f"{comparison_path}.vessels[{vessel_index}]"
            vessel = _require_object(vessel_value, vessel_path)
            _require_keys(
                vessel,
                ("name", "status", "evidence_artifact_path", "checks"),
                vessel_path,
            )
            _require_non_empty_string(vessel.get("name"), f"{vessel_path}.name")
            _require_non_empty_string(
                vessel.get("evidence_artifact_path"),
                f"{vessel_path}.evidence_artifact_path",
            )
            _require_allowed_value(
                vessel.get("status"),
                PREFLIGHT_STATUSES,
                f"{vessel_path}.status",
            )
            _validate_preflight_summary_checks(vessel["checks"], vessel_path)


def validate_course_handoff_document(document: dict[str, Any]) -> None:
    _require_object(document, "course handoff")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "status",
            "adapter",
            "tasks",
            "comparisons",
            "expected_outputs",
            "grading",
        ),
        "course handoff",
    )
    _require_schema(document, COURSE_HANDOFF_SCHEMA, "course handoff")
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], key)
    _require_allowed_value(document["status"], {"planned"}, "status")
    _validate_course_adapter_fields(
        _require_object(document["adapter"], "adapter"),
        "adapter",
    )
    _validate_course_handoff_tasks(document["tasks"])
    _validate_course_handoff_comparisons(document["comparisons"])
    _validate_expected_course_handoff_outputs(document["expected_outputs"])
    _validate_course_handoff_grading(document["grading"])
    if "export" in document:
        _validate_export_attribution(document["export"], "export")


def validate_run_index_document(document: dict[str, Any]) -> None:
    _require_object(document, "run index")
    _require_keys(
        document,
        (
            "schema",
            "run_kind",
            "status",
            "updated_at",
            "config_path",
            "logbook",
            "regatta",
            "course",
            "comparisons",
            "artifacts",
        ),
        "run index",
    )
    _require_schema(document, RUN_INDEX_SCHEMA, "run index")
    _require_allowed_value(
        document["run_kind"],
        RUN_INDEX_RUN_KINDS,
        "run index.run_kind",
    )
    for key in ("status", "updated_at", "config_path", "logbook", "regatta", "course"):
        _require_non_empty_string(document[key], f"run index.{key}")
    comparisons = _require_list(document["comparisons"], "run index.comparisons")
    for index, comparison_value in enumerate(comparisons):
        comparison_path = f"run index.comparisons[{index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(comparison, ("name", "course", "vessels"), comparison_path)
        _require_non_empty_string(comparison["name"], f"{comparison_path}.name")
        _require_non_empty_string(comparison["course"], f"{comparison_path}.course")
        vessels = _require_list(comparison["vessels"], f"{comparison_path}.vessels")
        if not vessels:
            raise SchemaValidationError(
                f"{comparison_path}.vessels must contain at least one vessel"
            )
        for vessel_index, vessel in enumerate(vessels):
            _require_non_empty_string(
                vessel,
                f"{comparison_path}.vessels[{vessel_index}]",
            )
    artifacts = _require_object(document["artifacts"], "run index.artifacts")
    for name, artifact_value in artifacts.items():
        artifact_path = f"run index.artifacts.{name}"
        artifact = _require_object(artifact_value, artifact_path)
        _require_keys(artifact, ("path", "present"), artifact_path)
        _require_non_empty_string(artifact["path"], f"{artifact_path}.path")
        if not isinstance(artifact["present"], bool):
            raise SchemaValidationError(f"{artifact_path}.present must be a boolean")


def validate_benchmark_grading_collection_document(document: dict[str, Any]) -> None:
    _require_object(document, "grading collection")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "adapter",
            "status",
            "summary",
            "next_steps",
            "comparisons",
        ),
        "grading collection",
    )
    _require_schema(document, BENCHMARK_GRADING_COLLECTION_SCHEMA, "grading collection")
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], f"grading collection.{key}")
    _validate_course_adapter_summary(
        _require_object(document["adapter"], "grading collection.adapter"),
        "grading collection.adapter",
    )
    _require_allowed_value(
        document["status"],
        BENCHMARK_GRADING_COLLECTION_STATUSES,
        "grading collection.status",
    )
    summary = _require_object(document["summary"], "grading collection.summary")
    for key in (
        "total_vessels",
        "completed_launches",
        "collected_reports",
        "missing_native_reports",
        "invalid_native_reports",
        "skipped_vessels",
    ):
        _require_keys(summary, (key,), "grading collection.summary")
        _require_non_negative_int(summary[key], f"grading collection.summary.{key}")
    _require_list(document["next_steps"], "grading collection.next_steps")
    comparisons = _require_list(
        document["comparisons"], "grading collection.comparisons"
    )
    for index, comparison_value in enumerate(comparisons):
        comparison_path = f"grading collection.comparisons[{index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(
            comparison, ("name", "course", "status", "vessels"), comparison_path
        )
        _require_non_empty_string(comparison["name"], f"{comparison_path}.name")
        _require_non_empty_string(comparison["course"], f"{comparison_path}.course")
        _require_allowed_value(
            comparison["status"],
            BENCHMARK_GRADING_COLLECTION_STATUSES,
            f"{comparison_path}.status",
        )
        vessels = _require_list(comparison["vessels"], f"{comparison_path}.vessels")
        for vessel_index, vessel_value in enumerate(vessels):
            vessel_path = f"{comparison_path}.vessels[{vessel_index}]"
            vessel = _require_object(vessel_value, vessel_path)
            _require_keys(vessel, ("name", "launch_status", "status"), vessel_path)
            _require_non_empty_string(vessel["name"], f"{vessel_path}.name")
            _require_non_empty_string(
                vessel["launch_status"], f"{vessel_path}.launch_status"
            )
            _require_allowed_value(
                vessel["status"],
                BENCHMARK_GRADING_COLLECTION_VESSEL_STATUSES,
                f"{vessel_path}.status",
            )
            if vessel["status"] == "collected":
                _require_keys(
                    vessel,
                    (
                        "native_report_path",
                        "grading_report_path",
                        "submitted_instances",
                        "resolved_instances",
                        "resolution_rate",
                    ),
                    vessel_path,
                )
                for key in ("native_report_path", "grading_report_path"):
                    _require_non_empty_string(vessel[key], f"{vessel_path}.{key}")
                for key in ("submitted_instances", "resolved_instances"):
                    _require_non_negative_int(vessel[key], f"{vessel_path}.{key}")
                _require_non_negative_number(
                    vessel["resolution_rate"], f"{vessel_path}.resolution_rate"
                )


def validate_real_benchmark_repetitions_document(document: dict[str, Any]) -> None:
    _require_object(document, "repetitions")
    _require_keys(
        document,
        (
            "schema",
            "status",
            "regatta",
            "course",
            "surfaces",
            "summary",
            "runs",
            "artifacts",
            "next_steps",
        ),
        "repetitions",
    )
    _require_schema(document, REAL_BENCHMARK_REPETITIONS_SCHEMA, "repetitions")
    _require_allowed_value(
        document["status"],
        REAL_BENCHMARK_REPETITIONS_STATUSES,
        "repetitions.status",
    )
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], f"repetitions.{key}")
    _require_object(document["surfaces"], "repetitions.surfaces")
    summary = _require_object(document["summary"], "repetitions.summary")
    for key in ("repetitions", "completed_runs", "failed_runs", "aggregate_logbooks"):
        _require_keys(summary, (key,), "repetitions.summary")
        _require_non_negative_int(summary[key], f"repetitions.summary.{key}")
    runs = _require_list(document["runs"], "repetitions.runs")
    for index, run_value in enumerate(runs):
        run_path = f"repetitions.runs[{index}]"
        run = _require_object(run_value, run_path)
        _require_keys(
            run,
            ("index", "logbook", "status", "scorecard_present", "artifacts"),
            run_path,
        )
        _require_non_negative_int(run["index"], f"{run_path}.index")
        _require_non_empty_string(run["logbook"], f"{run_path}.logbook")
        _require_non_empty_string(run["status"], f"{run_path}.status")
        if not isinstance(run["scorecard_present"], bool):
            raise SchemaValidationError(
                f"{run_path}.scorecard_present must be a boolean"
            )
        _require_string_mapping(run["artifacts"], f"{run_path}.artifacts")
    _require_string_mapping(document["artifacts"], "repetitions.artifacts")
    _require_list(document["next_steps"], "repetitions.next_steps")
    if "agent" in document:
        _require_non_empty_string(document["agent"], "repetitions.agent")
    if "aggregate_summary" in document:
        _require_object(document["aggregate_summary"], "repetitions.aggregate_summary")


def validate_benchmark_aggregate_document(document: dict[str, Any]) -> None:
    _require_object(document, "benchmark aggregate")
    _require_keys(
        document,
        ("schema", "regatta", "course", "run_count", "logbooks", "comparisons"),
        "benchmark aggregate",
    )
    _require_schema(document, BENCHMARK_AGGREGATE_SCHEMA, "benchmark aggregate")
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], f"benchmark aggregate.{key}")
    run_count = document["run_count"]
    if not isinstance(run_count, int) or run_count < 1:
        raise SchemaValidationError(
            "benchmark aggregate.run_count must be an integer >= 1"
        )
    logbooks = _require_list(document["logbooks"], "benchmark aggregate.logbooks")
    for index, logbook in enumerate(logbooks):
        _require_non_empty_string(logbook, f"benchmark aggregate.logbooks[{index}]")
    if len(logbooks) != run_count:
        raise SchemaValidationError(
            "benchmark aggregate.run_count must match the number of logbooks"
        )
    comparisons = _require_list(
        document["comparisons"], "benchmark aggregate.comparisons"
    )
    for index, comparison_value in enumerate(comparisons):
        comparison_path = f"benchmark aggregate.comparisons[{index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(
            comparison,
            ("name", "baseline", "challenger", "vessels", "delta"),
            comparison_path,
        )
        for key in ("name", "baseline", "challenger"):
            _require_non_empty_string(comparison[key], f"{comparison_path}.{key}")
        vessels = _require_list(comparison["vessels"], f"{comparison_path}.vessels")
        for vessel_index, vessel_value in enumerate(vessels):
            vessel_path = f"{comparison_path}.vessels[{vessel_index}]"
            vessel = _require_object(vessel_value, vessel_path)
            _require_keys(vessel, ("name",), vessel_path)
            _require_non_empty_string(vessel["name"], f"{vessel_path}.name")
            for key in (
                "runs",
                "eligible_runs",
                "measured_runs",
                "submitted_instances",
                "resolved_instances",
                "usage_runs",
                "total_tokens",
                "total_distinct_tool_uses",
            ):
                _require_keys(vessel, (key,), vessel_path)
                _require_non_negative_int(vessel[key], f"{vessel_path}.{key}")
            for key in ("resolution_rate", "total_cost", "total_duration_seconds"):
                _require_keys(vessel, (key,), vessel_path)
                _require_non_negative_number(vessel[key], f"{vessel_path}.{key}")
        _require_object(comparison["delta"], f"{comparison_path}.delta")
        # Per-run details and statistics blocks postdate the aggregate
        # artifact; older logbooks lack them and the renderer enriches,
        # so they validate when present.
        if "runs" in comparison:
            _require_list(comparison["runs"], f"{comparison_path}.runs")
        if "delta_statistics" in comparison:
            _require_object(
                comparison["delta_statistics"], f"{comparison_path}.delta_statistics"
            )
        if "paired_statistics" in comparison:
            _validate_paired_statistics(
                comparison["paired_statistics"],
                f"{comparison_path}.paired_statistics",
            )


def _validate_paired_statistics(value: Any, path: str) -> None:
    statistics = _require_object(value, path)
    _require_keys(
        statistics,
        (
            "baseline_vessel",
            "challenger_vessel",
            "shared_task_attempts",
            "concordant_resolved",
            "concordant_unresolved",
            "discordant_baseline_only",
            "discordant_challenger_only",
            "discordant_by_task",
            "grade",
            "p_value",
        ),
        path,
    )
    for key in ("baseline_vessel", "challenger_vessel"):
        _require_non_empty_string(statistics[key], f"{path}.{key}")
    for key in (
        "shared_task_attempts",
        "concordant_resolved",
        "concordant_unresolved",
        "discordant_baseline_only",
        "discordant_challenger_only",
    ):
        _require_non_negative_int(statistics[key], f"{path}.{key}")
    tasks = _require_list(
        statistics["discordant_by_task"], f"{path}.discordant_by_task"
    )
    for index, task_value in enumerate(tasks):
        task_path = f"{path}.discordant_by_task[{index}]"
        task = _require_object(task_value, task_path)
        _require_keys(task, ("task", "baseline_only", "challenger_only"), task_path)
        _require_non_empty_string(task["task"], f"{task_path}.task")
        for key in ("baseline_only", "challenger_only"):
            _require_non_negative_int(task[key], f"{task_path}.{key}")
    _require_allowed_value(statistics["grade"], EVIDENCE_GRADES, f"{path}.grade")
    p_value = statistics["p_value"]
    if not isinstance(p_value, int | float) or not 0.0 <= float(p_value) <= 1.0:
        raise SchemaValidationError(f"{path}.p_value must be a number between 0 and 1")


def validate_terminal_bench_job_document(document: dict[str, Any]) -> None:
    _require_object(document, "terminal-bench job")
    _require_keys(
        document,
        (
            "schema",
            "dataset",
            "tasks",
            "agent",
            "launcher_image",
            "secret_env",
            "vessel",
        ),
        "terminal-bench job",
    )
    _require_schema(document, TERMINAL_BENCH_JOB_SCHEMA, "terminal-bench job")
    dataset = _require_object(document["dataset"], "terminal-bench job.dataset")
    if "path" in dataset or "digest" in dataset:
        _require_keys(dataset, ("path", "digest"), "terminal-bench job.dataset")
        for key in ("path", "digest"):
            _require_non_empty_string(dataset[key], f"terminal-bench job.dataset.{key}")
    else:
        _require_keys(dataset, ("name", "version"), "terminal-bench job.dataset")
        for key in ("name", "version"):
            _require_non_empty_string(dataset[key], f"terminal-bench job.dataset.{key}")
    tasks = _require_list(document["tasks"], "terminal-bench job.tasks")
    if not tasks:
        raise SchemaValidationError(
            "terminal-bench job.tasks must contain at least one task"
        )
    for index, task in enumerate(tasks):
        _require_non_empty_string(task, f"terminal-bench job.tasks[{index}]")
    agent = _require_object(document["agent"], "terminal-bench job.agent")
    _require_keys(
        agent,
        (
            "name",
            "import_path",
            "version",
            "model",
            "env",
            "mcp_servers",
            "rigging_steps",
        ),
        "terminal-bench job.agent",
    )
    for key in ("name", "import_path", "version", "model"):
        _require_non_empty_string(agent[key], f"terminal-bench job.agent.{key}")
    _require_string_mapping(agent["env"], "terminal-bench job.agent.env")
    for key in ("mcp_servers", "rigging_steps"):
        entries = _require_list(agent[key], f"terminal-bench job.agent.{key}")
        for index, entry in enumerate(entries):
            _require_object(entry, f"terminal-bench job.agent.{key}[{index}]")
    if "declaration" in agent:
        _require_object(agent["declaration"], "terminal-bench job.agent.declaration")
    _require_non_empty_string(
        document["launcher_image"], "terminal-bench job.launcher_image"
    )
    secret_env = _require_list(document["secret_env"], "terminal-bench job.secret_env")
    for index, name in enumerate(secret_env):
        _require_non_empty_string(name, f"terminal-bench job.secret_env[{index}]")
    _require_non_empty_string(document["vessel"], "terminal-bench job.vessel")


def validate_course_grading_report_document(document: dict[str, Any]) -> None:
    _require_object(document, "grading report")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "adapter",
            "dataset",
            "split",
            "status",
            "source_report_path",
            "candidate_patches_path",
            "submitted_instances",
            "resolved_instances",
            "resolution_rate",
            "native_report",
        ),
        "grading report",
    )
    _require_allowed_value(
        document["schema"], COURSE_GRADING_SCHEMAS, "grading report.schema"
    )
    for key in (
        "regatta",
        "course",
        "adapter",
        "dataset",
        "split",
        "source_report_path",
        "candidate_patches_path",
    ):
        _require_non_empty_string(document[key], f"grading report.{key}")
    _require_allowed_value(document["status"], {"validated"}, "grading report.status")
    for key in ("submitted_instances", "resolved_instances"):
        _require_non_negative_int(document[key], f"grading report.{key}")
    _require_non_negative_number(
        document["resolution_rate"], "grading report.resolution_rate"
    )
    _require_object(document["native_report"], "grading report.native_report")
    if "vessel" in document:
        _require_non_empty_string(document["vessel"], "grading report.vessel")


def validate_real_benchmark_eval_document(document: dict[str, Any]) -> None:
    _require_object(document, "real benchmark eval")
    _require_keys(
        document,
        ("schema", "status", "regatta", "course"),
        "real benchmark eval",
    )
    _require_schema(document, REAL_BENCHMARK_EVAL_SCHEMA, "real benchmark eval")
    for key in ("status", "regatta", "course"):
        _require_non_empty_string(document[key], f"real benchmark eval.{key}")


def validate_benchmark_scorecard_document(document: dict[str, Any]) -> None:
    _require_object(document, "benchmark scorecard")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "adapter",
            "status",
            "summary",
            "comparisons",
        ),
        "benchmark scorecard",
    )
    _require_schema(document, BENCHMARK_SCORECARD_SCHEMA, "benchmark scorecard")
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], key)
    _validate_course_adapter_summary(
        _require_object(document["adapter"], "adapter"),
        "adapter",
    )
    _require_allowed_value(
        document["status"],
        BENCHMARK_SCORECARD_STATUSES,
        "status",
    )
    _validate_benchmark_scorecard_top_level_summary(document["summary"])
    _validate_benchmark_scorecard_comparisons(document["comparisons"])
    _validate_benchmark_scorecard_top_level_summary_matches_comparisons(
        document["summary"],
        document["comparisons"],
    )


def validate_benchmark_execution_plan_document(document: dict[str, Any]) -> None:
    _require_object(document, "benchmark execution plan")
    _require_keys(
        document,
        ("schema", "regatta", "course", "adapter", "status", "comparisons"),
        "benchmark execution plan",
    )
    _require_schema(
        document,
        BENCHMARK_EXECUTION_PLAN_SCHEMA,
        "benchmark execution plan",
    )
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], key)
    _validate_course_adapter_fields(
        _require_object(document["adapter"], "adapter"),
        "adapter",
    )
    _require_allowed_value(
        document["status"],
        BENCHMARK_EXECUTION_PLAN_STATUSES,
        "status",
    )
    _validate_benchmark_execution_plan_comparisons(document["comparisons"])


def validate_benchmark_readiness_summary_document(document: dict[str, Any]) -> None:
    _require_object(document, "benchmark readiness summary")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "status",
            "total_vessels",
            "launchable_vessels",
            "graded_vessels",
            "blocked_vessel_count",
            "blocked_vessels",
        ),
        "benchmark readiness summary",
    )
    _require_schema(
        document,
        BENCHMARK_READINESS_SUMMARY_SCHEMA,
        "benchmark readiness summary",
    )
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], key)
    _require_allowed_value(
        document["status"],
        BENCHMARK_EXECUTION_PLAN_STATUSES,
        "status",
    )
    for key in (
        "total_vessels",
        "launchable_vessels",
        "graded_vessels",
        "blocked_vessel_count",
    ):
        value = document[key]
        if not isinstance(value, int) or value < 0:
            raise SchemaValidationError(f"{key} must be an integer >= 0")
    blocked_vessels = _require_list(document["blocked_vessels"], "blocked_vessels")
    if document["blocked_vessel_count"] != len(blocked_vessels):
        raise SchemaValidationError(
            "blocked_vessel_count must equal blocked_vessels length"
        )
    expected_total = (
        document["launchable_vessels"]
        + document["graded_vessels"]
        + document["blocked_vessel_count"]
    )
    if document["total_vessels"] != expected_total:
        raise SchemaValidationError(
            "total_vessels must equal launchable_vessels + graded_vessels + "
            "blocked_vessel_count"
        )
    for index, vessel_value in enumerate(blocked_vessels):
        _validate_benchmark_readiness_blocked_vessel(
            vessel_value,
            f"blocked_vessels[{index}]",
        )


def validate_benchmark_launcher_handoff_document(document: dict[str, Any]) -> None:
    _require_object(document, "benchmark launcher handoff")
    _require_keys(
        document,
        ("schema", "regatta", "course", "adapter", "status", "comparisons"),
        "benchmark launcher handoff",
    )
    _require_schema(
        document,
        BENCHMARK_LAUNCHER_HANDOFF_SCHEMA,
        "benchmark launcher handoff",
    )
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], key)
    _validate_course_adapter_fields(
        _require_object(document["adapter"], "adapter"),
        "adapter",
    )
    _require_allowed_value(
        document["status"],
        BENCHMARK_LAUNCHER_HANDOFF_STATUSES,
        "status",
    )
    _validate_benchmark_launcher_handoff_comparisons(document["comparisons"])


def validate_benchmark_launch_result_document(document: dict[str, Any]) -> None:
    _require_object(document, "benchmark launch result")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "adapter",
            "status",
            "summary",
            "comparisons",
        ),
        "benchmark launch result",
    )
    _require_schema(
        document,
        BENCHMARK_LAUNCH_RESULT_SCHEMA,
        "benchmark launch result",
    )
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], key)
    _validate_course_adapter_fields(
        _require_object(document["adapter"], "adapter"),
        "adapter",
    )
    _require_allowed_value(
        document["status"],
        BENCHMARK_LAUNCH_RESULT_STATUSES,
        "status",
    )
    _validate_benchmark_launch_result_summary(document["summary"])
    _validate_benchmark_launch_result_comparisons(document["comparisons"])
    _validate_benchmark_launch_result_summary_matches_comparisons(
        document["summary"],
        document["comparisons"],
    )


def _validate_benchmark_launch_result_summary_matches_comparisons(
    summary: dict[str, Any],
    comparisons: list[Any],
) -> None:
    statuses = [
        str(vessel["status"])
        for comparison in comparisons
        for vessel in comparison["vessels"]
    ]
    expected = {
        "total_vessels": len(statuses),
        "completed_launches": statuses.count("completed"),
        "failed_launches": statuses.count("failed"),
        "skipped_vessels": statuses.count("skipped"),
    }
    expected["launched_vessels"] = (
        expected["completed_launches"] + expected["failed_launches"]
    )
    for key, expected_value in expected.items():
        if summary[key] != expected_value:
            raise SchemaValidationError(f"summary.{key} must equal {expected_value}")


def validate_runtime_instances_document(document: dict[str, Any]) -> None:
    _require_object(document, "runtime instances")
    _require_keys(
        document,
        ("schema", "regatta", "course", "mode", "workspace_path", "comparisons"),
        "runtime instances",
    )
    _require_schema(document, RUNTIME_INSTANCES_SCHEMA, "runtime instances")
    for key in ("regatta", "course", "workspace_path"):
        _require_non_empty_string(document[key], key)
    _require_allowed_value(document["mode"], {"dry-run"}, "mode")
    _validate_runtime_instances_comparisons(document["comparisons"])


def validate_task_attempt_document(document: dict[str, Any]) -> None:
    _require_object(document, "task attempt")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "comparison",
            "vessel",
            "model",
            "rigging",
            "runtime",
            "status",
            "task",
            "runtime_context",
            "prompt",
            "agent",
            "metrics",
            "secret_refs",
        ),
        "task attempt",
    )
    _require_schema(document, TASK_ATTEMPT_SCHEMA, "task attempt")
    for key in (
        "regatta",
        "course",
        "comparison",
        "vessel",
        "model",
        "runtime",
        "prompt",
    ):
        _require_non_empty_string(document[key], key)
    _require_string_list(document["rigging"], "rigging")
    _require_allowed_value(document["status"], TASK_ATTEMPT_STATUSES, "status")
    _validate_task_attempt_task(document["task"])
    if "provenance" in document:
        _validate_task_attempt_provenance(document["provenance"])
    _validate_task_attempt_runtime_context(document["runtime_context"])
    _validate_task_attempt_agent(document["agent"])
    _validate_task_attempt_metrics(document["metrics"])
    _validate_redacted_secret_refs(document["secret_refs"], "secret_refs")
    if "tool_expectations" in document:
        _validate_tool_expectations(document["tool_expectations"])


def _validate_tool_expectations(value: Any) -> None:
    expectations = _require_list(value, "tool_expectations")
    for index, expectation_value in enumerate(expectations):
        path = f"tool_expectations[{index}]"
        expectation = _require_object(expectation_value, path)
        _require_keys(expectation, ("tool", "kind", "expected_calls"), path)
        _require_non_empty_string(expectation.get("tool"), f"{path}.tool")
        _require_non_empty_string(expectation.get("kind"), f"{path}.kind")
        expected_calls = _require_list(
            expectation.get("expected_calls"),
            f"{path}.expected_calls",
        )
        if not expected_calls:
            raise SchemaValidationError(
                f"{path}.expected_calls must contain at least one call"
            )
        for call in expected_calls:
            _require_non_empty_string(call, f"{path}.expected_calls")


# These fields were named for tool calls but always held distinct-tool
# counts, because producers deduplicate tool names. Logbooks written
# before the rename are still read — recorded baselines and repetition
# aggregates depend on it — so their names are accepted and upgraded.
LEGACY_FIELD_NAMES = {
    "tool_call_count": "distinct_tool_uses",
    "tool_call_counts": "attempts_by_tool",
    "total_tool_calls": "total_distinct_tool_uses",
}


def normalize_task_attempt_scorecard(document: dict[str, Any]) -> dict[str, Any]:
    """Rewrite pre-rename field names so readers see one vocabulary."""

    def upgrade(payload: dict[str, Any]) -> dict[str, Any]:
        upgraded = dict(payload)
        for legacy, current in LEGACY_FIELD_NAMES.items():
            if legacy in upgraded and current not in upgraded:
                upgraded[current] = upgraded.pop(legacy)
            else:
                upgraded.pop(legacy, None)
        return upgraded

    normalized = upgrade(document)
    if isinstance(normalized.get("summary"), dict):
        normalized["summary"] = upgrade(normalized["summary"])
    comparisons = []
    for comparison in normalized.get("comparisons", []):
        comparison = upgrade(comparison)
        if isinstance(comparison.get("summary"), dict):
            comparison["summary"] = upgrade(comparison["summary"])
        comparison["vessels"] = [
            upgrade(vessel) for vessel in comparison.get("vessels", [])
        ]
        comparisons.append(comparison)
    if comparisons:
        normalized["comparisons"] = comparisons
    return normalized


def validate_task_attempt_scorecard_document(document: dict[str, Any]) -> None:
    document = normalize_task_attempt_scorecard(document)
    _require_object(document, "task attempt scorecard")
    _require_keys(
        document,
        ("schema", "regatta", "course", "status", "summary", "comparisons"),
        "task attempt scorecard",
    )
    _require_schema(
        document,
        TASK_ATTEMPT_SCORECARD_SCHEMA,
        "task attempt scorecard",
    )
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], key)
    _require_allowed_value(
        document["status"],
        TASK_ATTEMPT_SCORECARD_STATUSES,
        "status",
    )
    _validate_task_attempt_scorecard_summary(document["summary"], "summary")
    _validate_task_attempt_scorecard_comparisons(document["comparisons"])
    _validate_task_attempt_scorecard_summaries_match_details(document)


# Count fields whose summary value must equal the sum over detail rows,
# as (summary key, vessel key). Float fields (cost, duration) are excluded:
# the writer rounds them, so equality is not part of the contract.
_TASK_ATTEMPT_SUMMARY_SUM_FIELDS = (
    ("total_attempts", "task_attempts"),
    ("completed_attempts", "completed_attempts"),
    ("failed_attempts", "failed_attempts"),
    ("total_distinct_tool_uses", "distinct_tool_uses"),
    ("total_tokens", "total_tokens"),
)


def _validate_task_attempt_scorecard_summaries_match_details(
    document: dict[str, Any],
) -> None:
    comparisons = document["comparisons"]
    for index, comparison in enumerate(comparisons):
        _validate_task_attempt_summary_matches_vessels(
            comparison["summary"],
            comparison["vessels"],
            f"comparisons[{index}].summary",
        )
    all_vessels = [
        vessel for comparison in comparisons for vessel in comparison["vessels"]
    ]
    summary = document["summary"]
    _validate_task_attempt_summary_matches_vessels(summary, all_vessels, "summary")
    if "total_comparisons" in summary and summary["total_comparisons"] != len(
        comparisons
    ):
        raise SchemaValidationError(
            f"summary.total_comparisons must equal {len(comparisons)}"
        )


def _validate_task_attempt_summary_matches_vessels(
    summary: dict[str, Any],
    vessels: list[dict[str, Any]],
    path: str,
) -> None:
    expected: dict[str, int] = {"total_vessels": len(vessels)}
    for summary_key, vessel_key in _TASK_ATTEMPT_SUMMARY_SUM_FIELDS:
        expected[summary_key] = sum(int(vessel[vessel_key]) for vessel in vessels)
    for key, expected_value in expected.items():
        if summary[key] != expected_value:
            raise SchemaValidationError(f"{path}.{key} must equal {expected_value}")


def validate_smoke_readiness_report_document(document: dict[str, Any]) -> None:
    _require_object(document, "smoke readiness report")
    _require_keys(
        document,
        ("schema", "regatta", "course", "status", "summary", "comparisons"),
        "smoke readiness report",
    )
    _require_schema(
        document,
        SMOKE_READINESS_REPORT_SCHEMA,
        "smoke readiness report",
    )
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], key)
    _require_allowed_value(
        document["status"], SMOKE_READINESS_REPORT_STATUSES, "status"
    )
    _validate_smoke_readiness_summary(document["summary"], "summary")
    _validate_smoke_readiness_comparisons(document["comparisons"])


def validate_real_smoke_runbook_document(document: dict[str, Any]) -> None:
    _require_object(document, "real smoke runbook")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "agent",
            "secret_placeholders",
            "steps",
            "artifacts",
        ),
        "real smoke runbook",
    )
    _require_schema(document, REAL_SMOKE_RUNBOOK_SCHEMA, "real smoke runbook")
    for key in ("regatta", "course", "agent"):
        _require_non_empty_string(document[key], key)
    _validate_real_smoke_secret_placeholders(document["secret_placeholders"])
    _validate_real_smoke_runbook_steps(document["steps"])
    _validate_real_smoke_runbook_artifacts(document["artifacts"])


def _validate_real_smoke_secret_placeholders(value: Any) -> None:
    placeholders = _require_list(value, "secret_placeholders")
    for index, placeholder_value in enumerate(placeholders):
        path = f"secret_placeholders[{index}]"
        placeholder = _require_object(placeholder_value, path)
        _require_keys(placeholder, ("name", "source", "ref", "argument"), path)
        for key in ("name", "source", "ref", "argument"):
            _require_non_empty_string(placeholder.get(key), f"{path}.{key}")


def _validate_real_smoke_runbook_steps(value: Any) -> None:
    steps = _require_list(value, "steps")
    if not steps:
        raise SchemaValidationError("steps must contain at least one step")
    for index, step_value in enumerate(steps):
        path = f"steps[{index}]"
        step = _require_object(step_value, path)
        _require_keys(step, ("name", "command", "artifacts"), path)
        for key in ("name", "command"):
            _require_non_empty_string(step.get(key), f"{path}.{key}")
        _require_string_list(step["artifacts"], f"{path}.artifacts")


def _validate_real_smoke_runbook_artifacts(value: Any) -> None:
    artifacts = _require_object(value, "artifacts")
    _require_keys(
        artifacts,
        (
            "preflight",
            "task_attempts",
            "task_attempt_scorecard",
            "smoke_readiness_report",
            "smoke_report",
            "real_smoke_runbook",
        ),
        "artifacts",
    )
    for key in ("preflight", "task_attempts"):
        _require_string_list(artifacts[key], f"artifacts.{key}")
    for key in (
        "task_attempt_scorecard",
        "smoke_readiness_report",
        "smoke_report",
        "real_smoke_runbook",
    ):
        _require_non_empty_string(artifacts.get(key), f"artifacts.{key}")


def validate_real_benchmark_runbook_document(document: dict[str, Any]) -> None:
    _require_object(document, "real benchmark runbook")
    _require_keys(
        document,
        (
            "schema",
            "regatta",
            "course",
            "agent",
            "secret_placeholders",
            "steps",
            "artifacts",
        ),
        "real benchmark runbook",
    )
    _require_schema(
        document,
        REAL_BENCHMARK_RUNBOOK_SCHEMA,
        "real benchmark runbook",
    )
    for key in ("regatta", "course", "agent"):
        _require_non_empty_string(document[key], key)
    _validate_real_smoke_secret_placeholders(document["secret_placeholders"])
    _validate_real_smoke_runbook_steps(document["steps"])
    _validate_real_benchmark_runbook_artifacts(document["artifacts"])


def _validate_real_benchmark_runbook_artifacts(value: Any) -> None:
    artifacts = _require_object(value, "artifacts")
    _require_keys(
        artifacts,
        (
            "course_handoff",
            "preflight",
            "preflight_evidence_report",
            "task_attempts",
            "task_attempt_scorecard",
            "candidate_patches",
            "runtime_instances",
            "benchmark_execution_plan",
            "benchmark_launcher_handoff",
            "benchmark_launch_result",
            "benchmark_grading_collection",
            "benchmark_scorecard",
            "benchmark_report",
            "real_benchmark_eval",
            "real_benchmark_runbook",
        ),
        "artifacts",
    )
    for key in ("preflight", "task_attempts", "candidate_patches"):
        _require_string_list(artifacts[key], f"artifacts.{key}")
    for key in (
        "course_handoff",
        "preflight_evidence_report",
        "task_attempt_scorecard",
        "runtime_instances",
        "benchmark_execution_plan",
        "benchmark_launcher_handoff",
        "benchmark_launch_result",
        "benchmark_grading_collection",
        "benchmark_scorecard",
        "benchmark_report",
        "real_benchmark_eval",
        "real_benchmark_runbook",
    ):
        _require_non_empty_string(artifacts.get(key), f"artifacts.{key}")


def _validate_smoke_readiness_summary(value: Any, path: str) -> None:
    summary = _require_object(value, path)
    for key in (
        "total_vessels",
        "ready_vessels",
        "blocked_vessels",
        "passed_preflight_vessels",
        "completed_task_attempt_vessels",
        "passed_agent_prompt_checks",
    ):
        _require_non_negative_int(summary.get(key), f"{path}.{key}")


def _validate_smoke_readiness_comparisons(value: Any) -> None:
    comparisons = _require_list(value, "comparisons")
    if not comparisons:
        raise SchemaValidationError("comparisons must contain at least one comparison")
    for comparison_index, comparison_value in enumerate(comparisons):
        comparison_path = f"comparisons[{comparison_index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(comparison, ("name", "status", "vessels"), comparison_path)
        _require_non_empty_string(comparison.get("name"), f"{comparison_path}.name")
        _require_allowed_value(
            comparison.get("status"),
            SMOKE_READINESS_REPORT_STATUSES,
            f"{comparison_path}.status",
        )
        vessels = _require_list(comparison["vessels"], f"{comparison_path}.vessels")
        if not vessels:
            raise SchemaValidationError(
                f"{comparison_path}.vessels must contain at least one vessel"
            )
        for vessel_index, vessel_value in enumerate(vessels):
            _validate_smoke_readiness_vessel(
                vessel_value,
                f"{comparison_path}.vessels[{vessel_index}]",
            )


def _validate_smoke_readiness_vessel(value: Any, path: str) -> None:
    vessel = _require_object(value, path)
    _require_keys(
        vessel,
        (
            "name",
            "status",
            "preflight_status",
            "task_attempt_status",
            "preflight_artifact_path",
            "task_attempt_artifact_paths",
            "agent_prompt_checks",
            "attempts_by_tool",
            "expected_tool_calls",
            "missing_expected_tool_calls",
            "reasons",
        ),
        path,
    )
    _require_non_empty_string(vessel.get("name"), f"{path}.name")
    _require_allowed_value(
        vessel.get("status"),
        SMOKE_READINESS_REPORT_VESSEL_STATUSES,
        f"{path}.status",
    )
    for key in ("preflight_status", "task_attempt_status", "preflight_artifact_path"):
        _require_non_empty_string(vessel.get(key), f"{path}.{key}")
    _require_string_list(
        vessel["task_attempt_artifact_paths"],
        f"{path}.task_attempt_artifact_paths",
    )
    agent_prompt_checks = _require_object(
        vessel["agent_prompt_checks"],
        f"{path}.agent_prompt_checks",
    )
    for key in ("total", "passed"):
        _require_non_negative_int(
            agent_prompt_checks.get(key),
            f"{path}.agent_prompt_checks.{key}",
        )
    _validate_tool_call_counts(vessel["attempts_by_tool"], f"{path}.attempts_by_tool")
    _require_string_list(vessel["expected_tool_calls"], f"{path}.expected_tool_calls")
    _require_string_list(
        vessel["missing_expected_tool_calls"],
        f"{path}.missing_expected_tool_calls",
    )
    _require_string_list(vessel["reasons"], f"{path}.reasons")


def _validate_task_attempt_scorecard_comparisons(value: Any) -> None:
    comparisons = _require_list(value, "comparisons")
    if not comparisons:
        raise SchemaValidationError("comparisons must contain at least one comparison")
    for index, comparison_value in enumerate(comparisons):
        comparison_path = f"comparisons[{index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(
            comparison,
            ("name", "summary", "vessels"),
            comparison_path,
        )
        _require_non_empty_string(
            comparison.get("name"),
            f"{comparison_path}.name",
        )
        _validate_task_attempt_scorecard_summary(
            comparison["summary"],
            f"{comparison_path}.summary",
        )
        vessels = _require_list(comparison["vessels"], f"{comparison_path}.vessels")
        if not vessels:
            raise SchemaValidationError(
                f"{comparison_path}.vessels must contain at least one vessel"
            )
        for vessel_index, vessel_value in enumerate(vessels):
            _validate_task_attempt_scorecard_vessel(
                vessel_value,
                f"{comparison_path}.vessels[{vessel_index}]",
            )


def _validate_task_attempt_scorecard_vessel(value: Any, path: str) -> None:
    vessel = _require_object(value, path)
    _require_keys(
        vessel,
        (
            "name",
            "status",
            "task_attempts",
            "completed_attempts",
            "failed_attempts",
            "success_rate",
            "distinct_tool_uses",
            "total_tokens",
            "total_duration_seconds",
            "artifact_paths",
        ),
        path,
    )
    _require_non_empty_string(vessel.get("name"), f"{path}.name")
    _require_allowed_value(
        vessel.get("status"),
        TASK_ATTEMPT_SCORECARD_VESSEL_STATUSES,
        f"{path}.status",
    )
    for key in (
        "task_attempts",
        "completed_attempts",
        "failed_attempts",
        "distinct_tool_uses",
        "total_tokens",
    ):
        _require_non_negative_int(vessel.get(key), f"{path}.{key}")
    _require_non_negative_number(vessel.get("success_rate"), f"{path}.success_rate")
    if "provenance" in vessel:
        _validate_collapsed_provenance(vessel["provenance"], f"{path}.provenance")
    _require_non_negative_number(
        vessel.get("total_duration_seconds"),
        f"{path}.total_duration_seconds",
    )
    if "harnesses" in vessel:
        _require_string_list(vessel.get("harnesses"), f"{path}.harnesses")
    if "total_cost" in vessel:
        _require_non_negative_number(vessel.get("total_cost"), f"{path}.total_cost")
    if "attempts_by_tool" in vessel:
        _validate_tool_call_counts(
            vessel.get("attempts_by_tool"),
            f"{path}.attempts_by_tool",
        )
    if "tool_invocations" in vessel:
        _validate_tool_invocations(
            vessel.get("tool_invocations"),
            f"{path}.tool_invocations",
        )
    if "usage_sources" in vessel:
        usage_sources = _require_list(
            vessel.get("usage_sources"),
            f"{path}.usage_sources",
        )
        for source in usage_sources:
            _require_allowed_value(
                source,
                METRICS_USAGE_SOURCES,
                f"{path}.usage_sources",
            )
    if "cost_sources" in vessel:
        cost_sources = _require_list(
            vessel.get("cost_sources"),
            f"{path}.cost_sources",
        )
        for source in cost_sources:
            _require_allowed_value(
                source,
                COST_SOURCES,
                f"{path}.cost_sources",
            )
    _require_string_list(vessel.get("artifact_paths"), f"{path}.artifact_paths")


def _validate_tool_invocations(value: Any, path: str) -> None:
    entries = _require_list(value, path)
    for index, entry_value in enumerate(entries):
        entry_path = f"{path}[{index}]"
        entry = _require_object(entry_value, entry_path)
        _require_keys(
            entry,
            (
                "tool",
                "kind",
                "expected_calls",
                "status",
                "attempts",
                "measured_attempts",
            ),
            entry_path,
        )
        _require_non_empty_string(entry.get("tool"), f"{entry_path}.tool")
        _require_non_empty_string(entry.get("kind"), f"{entry_path}.kind")
        _require_string_list(
            entry.get("expected_calls"),
            f"{entry_path}.expected_calls",
        )
        _require_allowed_value(
            entry.get("status"),
            {"measured", "unmeasured"},
            f"{entry_path}.status",
        )
        for key in ("attempts", "measured_attempts"):
            _require_non_negative_int(entry.get(key), f"{entry_path}.{key}")
        if "observed_tools" in entry:
            _require_string_list(
                entry.get("observed_tools"),
                f"{entry_path}.observed_tools",
            )
        if entry.get("status") == "unmeasured":
            continue
        _require_non_negative_int(
            entry.get("invoked_attempts"),
            f"{entry_path}.invoked_attempts",
        )
        _require_non_negative_number(
            entry.get("invocation_rate"),
            f"{entry_path}.invocation_rate",
        )
        _validate_rate_interval(
            entry.get("invocation_interval"),
            f"{entry_path}.invocation_interval",
        )
        if "completed_attempts" in entry:
            for key in ("completed_attempts", "invoked_completed_attempts"):
                _require_non_negative_int(entry.get(key), f"{entry_path}.{key}")
            _require_non_negative_number(
                entry.get("completed_invocation_rate"),
                f"{entry_path}.completed_invocation_rate",
            )
            _validate_rate_interval(
                entry.get("completed_invocation_interval"),
                f"{entry_path}.completed_invocation_interval",
            )


def _validate_task_attempt_scorecard_summary(value: Any, path: str) -> None:
    summary = _require_object(value, path)
    for key in (
        "total_vessels",
        "total_attempts",
        "completed_attempts",
        "failed_attempts",
        "total_distinct_tool_uses",
        "total_tokens",
    ):
        _require_non_negative_int(summary.get(key), f"{path}.{key}")
    _require_non_negative_number(
        summary.get("total_duration_seconds"),
        f"{path}.total_duration_seconds",
    )
    if "total_cost" in summary:
        _require_non_negative_number(summary.get("total_cost"), f"{path}.total_cost")
    if "attempts_by_tool" in summary:
        _validate_tool_call_counts(
            summary.get("attempts_by_tool"),
            f"{path}.attempts_by_tool",
        )
    if "total_comparisons" in summary:
        _require_non_negative_int(
            summary.get("total_comparisons"),
            f"{path}.total_comparisons",
        )


def _validate_tool_call_counts(value: Any, path: str) -> None:
    counts = _require_object(value, path)
    for tool_name, count in counts.items():
        if not isinstance(tool_name, str) or not tool_name:
            raise SchemaValidationError(f"{path} keys must be non-empty strings")
        _require_non_negative_int(count, f"{path}.{tool_name}")


def _validate_task_attempt_task(value: Any) -> None:
    task = _require_object(value, "task")
    _require_keys(task, ("id", "title", "difficulty"), "task")
    _require_non_empty_string(task.get("id"), "task.id")
    _require_non_empty_string(task.get("title"), "task.title")
    difficulty = task.get("difficulty")
    if not isinstance(difficulty, int) or difficulty < 1:
        raise SchemaValidationError("task.difficulty must be an integer >= 1")
    for field in ("repo", "repo_url", "base_commit", "problem_statement"):
        if field in task:
            _require_non_empty_string(task.get(field), f"task.{field}")
    if "expect_response" in task:
        _validate_expect_response(task["expect_response"], "task.expect_response")
    if "expect_tool_calls" in task:
        _validate_expect_tool_calls(
            task["expect_tool_calls"],
            "task.expect_tool_calls",
        )


def _validate_expect_response(value: Any, path: str) -> None:
    expectations = _require_object(value, path)
    if not expectations:
        raise SchemaValidationError(f"{path} must contain at least one field")
    for key, expected in expectations.items():
        if not isinstance(key, str) or not key:
            raise SchemaValidationError(f"{path} keys must be non-empty strings")
        if not isinstance(expected, str | bool | int | float):
            raise SchemaValidationError(
                f"{path}.{key} must be a string, boolean, integer, or number"
            )


def _validate_expect_tool_calls(value: Any, path: str) -> None:
    tool_calls = _require_list(value, path)
    for index, tool_call in enumerate(tool_calls):
        if not isinstance(tool_call, str) or not tool_call:
            raise SchemaValidationError(f"{path}[{index}] must be non-empty")


def _validate_task_attempt_provenance(value: Any) -> None:
    provenance = _require_object(value, "provenance")
    _require_keys(
        provenance,
        ("yacht", "harness", "model", "runtime", "tools"),
        "provenance",
    )
    yacht_block = _require_object(provenance["yacht"], "provenance.yacht")
    _require_non_empty_string(yacht_block.get("version"), "provenance.yacht.version")
    harness = _require_object(provenance["harness"], "provenance.harness")
    _require_keys(harness, ("name", "version"), "provenance.harness")
    _require_nullable_non_empty_string(harness["name"], "provenance.harness.name")
    _require_nullable_non_empty_string(harness["version"], "provenance.harness.version")
    model = _require_object(provenance["model"], "provenance.model")
    _require_keys(model, ("configured", "resolved"), "provenance.model")
    _require_non_empty_string(model["configured"], "provenance.model.configured")
    _require_nullable_non_empty_string(model["resolved"], "provenance.model.resolved")
    runtime = _require_object(provenance["runtime"], "provenance.runtime")
    _require_keys(runtime, ("backend", "image"), "provenance.runtime")
    _require_non_empty_string(runtime["backend"], "provenance.runtime.backend")
    _require_nullable_non_empty_string(runtime["image"], "provenance.runtime.image")
    tools = _require_list(provenance["tools"], "provenance.tools")
    for index, tool_value in enumerate(tools):
        tool_path = f"provenance.tools[{index}]"
        tool = _require_object(tool_value, tool_path)
        _require_keys(tool, ("name", "tools", "version", "source"), tool_path)
        _require_non_empty_string(tool["name"], f"{tool_path}.name")
        _require_string_list(tool["tools"], f"{tool_path}.tools")
        _require_nullable_non_empty_string(tool["version"], f"{tool_path}.version")
        _require_nullable_non_empty_string(tool["source"], f"{tool_path}.source")


def _require_nullable_non_empty_string(value: Any, path: str) -> None:
    if value is None:
        return
    _require_non_empty_string(value, path)


def _validate_collapsed_provenance(value: Any, path: str) -> None:
    provenance = _require_object(value, path)
    _require_keys(
        provenance,
        ("yacht", "harness", "model", "runtime", "tools", "mixed"),
        path,
    )
    for section, leaves in (
        ("yacht", ("version",)),
        ("harness", ("name", "version")),
        ("model", ("configured", "resolved")),
        ("runtime", ("backend", "image")),
    ):
        block = _require_object(provenance[section], f"{path}.{section}")
        for leaf in leaves:
            _require_nullable_non_empty_string(
                block.get(leaf), f"{path}.{section}.{leaf}"
            )
    if provenance["tools"] is not None:
        tools = _require_list(provenance["tools"], f"{path}.tools")
        for index, tool_value in enumerate(tools):
            tool_path = f"{path}.tools[{index}]"
            tool = _require_object(tool_value, tool_path)
            _require_keys(tool, ("name", "tools", "version", "source"), tool_path)
            _require_non_empty_string(tool["name"], f"{tool_path}.name")
            _require_string_list(tool["tools"], f"{tool_path}.tools")
            _require_nullable_non_empty_string(tool["version"], f"{tool_path}.version")
            _require_nullable_non_empty_string(tool["source"], f"{tool_path}.source")
    _require_string_list(provenance["mixed"], f"{path}.mixed")


def _validate_task_attempt_runtime_context(value: Any) -> None:
    context = _require_object(value, "runtime_context")
    _require_keys(
        context,
        (
            "backend",
            "temp_home",
            "workspace_path",
            "command_prefix",
            "command",
            "cleanup_paths",
        ),
        "runtime_context",
    )
    for key in ("backend", "temp_home", "workspace_path"):
        _require_non_empty_string(context.get(key), f"runtime_context.{key}")
    for key in ("harness", "agent"):
        if key in context:
            _require_non_empty_string(context.get(key), f"runtime_context.{key}")
    _require_string_list(
        context.get("command_prefix"),
        "runtime_context.command_prefix",
    )
    _require_string_list(context.get("command"), "runtime_context.command")
    _require_string_list(
        context.get("cleanup_paths"),
        "runtime_context.cleanup_paths",
    )
    if "setup_results" in context:
        results = _require_list(
            context["setup_results"],
            "runtime_context.setup_results",
        )
        for index, result_value in enumerate(results):
            result_path = f"runtime_context.setup_results[{index}]"
            result = _require_object(result_value, result_path)
            _require_keys(
                result,
                ("origin", "origin_name", "action", "target", "argv", "exit_code"),
                result_path,
            )
            for key in ("origin", "origin_name", "action", "target"):
                _require_non_empty_string(result.get(key), f"{result_path}.{key}")
            _require_string_list(result.get("argv"), f"{result_path}.argv")
            exit_code = result.get("exit_code")
            if not isinstance(exit_code, int) or exit_code < 0:
                raise SchemaValidationError(
                    f"{result_path}.exit_code must be an integer >= 0"
                )


def _validate_task_attempt_agent(value: Any) -> None:
    agent = _require_object(value, "agent")
    _require_keys(
        agent,
        ("exit_code", "response", "tool_calls", "transcript_path"),
        "agent",
    )
    exit_code = agent.get("exit_code")
    if not isinstance(exit_code, int) or exit_code < 0:
        raise SchemaValidationError("agent.exit_code must be an integer >= 0")
    if not isinstance(agent.get("response"), str):
        raise SchemaValidationError("agent.response must be a string")
    _require_string_list(agent.get("tool_calls"), "agent.tool_calls")
    _require_non_empty_string(agent.get("transcript_path"), "agent.transcript_path")
    if "tool_call_evidence" in agent:
        _require_non_empty_string(
            agent.get("tool_call_evidence"),
            "agent.tool_call_evidence",
        )
    if "machine_evidence" in agent:
        _validate_task_attempt_machine_evidence(agent["machine_evidence"])


def _validate_task_attempt_machine_evidence(value: Any) -> None:
    evidence = _require_object(value, "agent.machine_evidence")
    if "format" in evidence:
        _require_non_empty_string(
            evidence.get("format"),
            "agent.machine_evidence.format",
        )
    if "event_count" in evidence:
        _require_non_negative_int(
            evidence.get("event_count"),
            "agent.machine_evidence.event_count",
        )
    for key in ("api", "provider", "model", "response_id"):
        if key in evidence:
            _require_non_empty_string(
                evidence.get(key),
                f"agent.machine_evidence.{key}",
            )
    for key in ("usage", "cost"):
        if key in evidence:
            _validate_numeric_evidence_map(
                evidence.get(key),
                f"agent.machine_evidence.{key}",
            )
    if "tool_calls" in evidence:
        _require_string_list(
            evidence.get("tool_calls"),
            "agent.machine_evidence.tool_calls",
        )


def _validate_numeric_evidence_map(value: Any, path: str) -> None:
    payload = _require_object(value, path)
    for key, numeric_value in payload.items():
        if not isinstance(key, str) or not key:
            raise SchemaValidationError(f"{path} keys must be non-empty strings")
        _require_non_negative_number(numeric_value, f"{path}.{key}")


def _validate_task_attempt_metrics(value: Any) -> None:
    metrics = _require_object(value, "metrics")
    if not isinstance(metrics.get("tokens"), int) or metrics["tokens"] < 0:
        raise SchemaValidationError("metrics.tokens must be an integer >= 0")
    if (
        not isinstance(metrics.get("duration_seconds"), int | float)
        or metrics["duration_seconds"] < 0
    ):
        raise SchemaValidationError("metrics.duration_seconds must be a number >= 0")
    if "usage_source" in metrics:
        _require_allowed_value(
            metrics.get("usage_source"),
            METRICS_USAGE_SOURCES,
            "metrics.usage_source",
        )


def _validate_course_handoff_tasks(value: Any) -> None:
    tasks = _require_list(value, "tasks")
    if not tasks:
        raise SchemaValidationError("tasks must contain at least one task")
    for index, task_value in enumerate(tasks):
        task = _require_object(task_value, f"tasks[{index}]")
        _require_keys(task, ("id", "title", "difficulty"), f"tasks[{index}]")
        _require_non_empty_string(task.get("id"), f"tasks[{index}].id")
        _require_non_empty_string(task.get("title"), f"tasks[{index}].title")
        difficulty = task.get("difficulty")
        if not isinstance(difficulty, int) or difficulty < 1:
            raise SchemaValidationError(
                f"tasks[{index}].difficulty must be an integer >= 1"
            )
        for field in ("repo", "repo_url", "base_commit", "problem_statement"):
            if field in task:
                _require_non_empty_string(task.get(field), f"tasks[{index}].{field}")
        if "expect_response" in task:
            _validate_expect_response(
                task["expect_response"],
                f"tasks[{index}].expect_response",
            )
        if "expect_tool_calls" in task:
            _validate_expect_tool_calls(
                task["expect_tool_calls"],
                f"tasks[{index}].expect_tool_calls",
            )


def _validate_course_handoff_comparisons(value: Any) -> None:
    comparisons = _require_list(value, "comparisons")
    if not comparisons:
        raise SchemaValidationError("comparisons must contain at least one comparison")
    for index, comparison_value in enumerate(comparisons):
        comparison = _require_object(comparison_value, f"comparisons[{index}]")
        _require_keys(
            comparison, ("name", "course", "vessels"), f"comparisons[{index}]"
        )
        _require_non_empty_string(comparison.get("name"), f"comparisons[{index}].name")
        _require_non_empty_string(
            comparison.get("course"),
            f"comparisons[{index}].course",
        )
        vessels = _require_list(
            comparison.get("vessels"),
            f"comparisons[{index}].vessels",
        )
        baseline = comparison.get("baseline")
        if baseline is None:
            if len(vessels) < 2:
                raise SchemaValidationError(
                    f"comparisons[{index}].vessels must contain at least two "
                    "vessels; to compare one live vessel against a stored "
                    "run, reference it with comparisons.baseline"
                )
        else:
            baseline_path = f"comparisons[{index}].baseline"
            baseline_object = _require_object(baseline, baseline_path)
            _require_keys(baseline_object, ("logbook", "vessel"), baseline_path)
            _require_non_empty_string(
                baseline_object.get("logbook"),
                f"{baseline_path}.logbook",
            )
            _require_non_empty_string(
                baseline_object.get("vessel"),
                f"{baseline_path}.vessel",
            )
            if len(vessels) != 1:
                raise SchemaValidationError(
                    f"comparisons[{index}].vessels must contain exactly one "
                    "live vessel when comparisons.baseline is set"
                )
        for vessel in vessels:
            _require_non_empty_string(vessel, f"comparisons[{index}].vessels")


def _validate_expected_course_handoff_outputs(value: Any) -> None:
    expected_outputs = _require_object(value, "expected_outputs")
    for key in ("candidate_patches", "grading_report"):
        _require_non_empty_string(
            expected_outputs.get(key),
            f"expected_outputs.{key}",
        )


def _validate_course_handoff_grading(value: Any) -> None:
    grading = _require_object(value, "grading")
    _require_keys(grading, ("delegated_to", "execution", "status"), "grading")
    _require_allowed_value(
        grading.get("delegated_to"),
        COURSE_ADAPTER_KINDS,
        "grading.delegated_to",
    )
    _require_allowed_value(
        grading.get("execution"),
        {f"{harness}-harness" for harness in COURSE_ADAPTER_HARNESSES},
        "grading.execution",
    )
    _require_allowed_value(grading.get("status"), {"planned"}, "grading.status")


VERDICT_GRADES = {
    "insufficient-evidence",
    "not-distinguishable",
    "evidence-of-difference",
}


def _validate_benchmark_scorecard_statistics(value: Any, path: str) -> None:
    statistics = _require_object(value, f"{path}.statistics")
    _require_keys(
        statistics,
        ("confidence_level", "rates", "paired"),
        f"{path}.statistics",
    )
    confidence = statistics.get("confidence_level")
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0.0 < float(confidence) < 1.0
    ):
        raise SchemaValidationError(
            f"{path}.statistics.confidence_level must be between 0 and 1"
        )
    rates = _require_object(statistics["rates"], f"{path}.statistics.rates")
    for vessel_name, rate_value in rates.items():
        rate_path = f"{path}.statistics.rates.{vessel_name}"
        rate = _require_object(rate_value, rate_path)
        _require_keys(
            rate,
            ("resolved_instances", "submitted_instances", "interval"),
            rate_path,
        )
        for key in ("resolved_instances", "submitted_instances"):
            _require_non_negative_int(rate.get(key), f"{rate_path}.{key}")
        _validate_rate_interval(rate.get("interval"), f"{rate_path}.interval")
    paired = _require_object(statistics["paired"], f"{path}.statistics.paired")
    _require_keys(
        paired,
        (
            "shared_tasks",
            "concordant_resolved",
            "concordant_unresolved",
            "discordant_baseline_only",
            "discordant_challenger_only",
            "p_value",
            "grade",
        ),
        f"{path}.statistics.paired",
    )
    for key in (
        "shared_tasks",
        "concordant_resolved",
        "concordant_unresolved",
        "discordant_baseline_only",
        "discordant_challenger_only",
    ):
        _require_non_negative_int(paired.get(key), f"{path}.statistics.paired.{key}")
    p_value = paired.get("p_value")
    if (
        not isinstance(p_value, (int, float))
        or isinstance(p_value, bool)
        or not 0.0 <= float(p_value) <= 1.0
    ):
        raise SchemaValidationError(
            f"{path}.statistics.paired.p_value must be between 0 and 1"
        )
    _require_allowed_value(
        paired.get("grade"),
        VERDICT_GRADES,
        f"{path}.statistics.paired.grade",
    )
    if "min_significant_discordant" in paired:
        _require_non_negative_int(
            paired.get("min_significant_discordant"),
            f"{path}.statistics.paired.min_significant_discordant",
        )
    for key in ("discordant_baseline_only_ids", "discordant_challenger_only_ids"):
        if key in paired:
            _require_string_list(paired.get(key), f"{path}.statistics.paired.{key}")
    if "repetition_guidance" in statistics:
        _validate_repetition_guidance(
            statistics["repetition_guidance"],
            f"{path}.statistics.repetition_guidance",
        )


def _validate_repetition_guidance(value: Any, path: str) -> None:
    guidance = _require_object(value, path)
    _require_keys(
        guidance,
        (
            "power_target",
            "significance_level",
            "observed_discordance_rate",
            "shared_tasks_per_run",
            "plans",
            "applies_to",
        ),
        path,
    )
    for key in ("power_target", "significance_level", "observed_discordance_rate"):
        rate = guidance.get(key)
        if (
            not isinstance(rate, (int, float))
            or isinstance(rate, bool)
            or not 0.0 <= float(rate) <= 1.0
        ):
            raise SchemaValidationError(f"{path}.{key} must be between 0 and 1")
    _require_non_negative_int(
        guidance.get("shared_tasks_per_run"),
        f"{path}.shared_tasks_per_run",
    )
    _require_non_empty_string(guidance.get("applies_to"), f"{path}.applies_to")
    if "observed_discordance_rate_interval" in guidance:
        _validate_rate_interval(
            guidance["observed_discordance_rate_interval"],
            f"{path}.observed_discordance_rate_interval",
        )
    plans = _require_list(guidance["plans"], f"{path}.plans")
    if not plans:
        raise SchemaValidationError(f"{path}.plans must contain at least one plan")
    for index, plan_value in enumerate(plans):
        plan_path = f"{path}.plans[{index}]"
        plan = _require_object(plan_value, plan_path)
        _require_keys(
            plan,
            ("assumed_favored_fraction", "discordant_pairs_needed"),
            plan_path,
        )
        fraction = plan.get("assumed_favored_fraction")
        if (
            not isinstance(fraction, (int, float))
            or isinstance(fraction, bool)
            or not 0.0 <= float(fraction) <= 1.0
        ):
            raise SchemaValidationError(
                f"{plan_path}.assumed_favored_fraction must be between 0 and 1"
            )
        pairs_needed = plan.get("discordant_pairs_needed")
        if pairs_needed is not None:
            _require_non_negative_int(
                pairs_needed,
                f"{plan_path}.discordant_pairs_needed",
            )
        if plan.get("repetitions") is not None:
            _require_non_negative_int(plan["repetitions"], f"{plan_path}.repetitions")
        if "repetitions_range" in plan:
            bounds = _require_object(
                plan["repetitions_range"],
                f"{plan_path}.repetitions_range",
            )
            for key in ("low", "high"):
                if bounds.get(key) is not None:
                    _require_non_negative_int(
                        bounds[key],
                        f"{plan_path}.repetitions_range.{key}",
                    )


def _validate_rate_interval(value: Any, path: str) -> None:
    if value is None:
        return
    interval = _require_object(value, path)
    _require_keys(interval, ("low", "high"), path)
    for key in ("low", "high"):
        bound = interval.get(key)
        if (
            not isinstance(bound, (int, float))
            or isinstance(bound, bool)
            or not 0.0 <= float(bound) <= 1.0
        ):
            raise SchemaValidationError(f"{path}.{key} must be between 0 and 1")


def _validate_benchmark_scorecard_comparisons(value: Any) -> None:
    comparisons = _require_list(value, "comparisons")
    if not comparisons:
        raise SchemaValidationError("comparisons must contain at least one comparison")
    for comparison_index, comparison_value in enumerate(comparisons):
        comparison_path = f"comparisons[{comparison_index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(
            comparison,
            ("name", "course", "summary", "delta", "vessels"),
            comparison_path,
        )
        _require_non_empty_string(comparison.get("name"), f"{comparison_path}.name")
        _require_non_empty_string(comparison.get("course"), f"{comparison_path}.course")
        _validate_benchmark_scorecard_summary(
            comparison["summary"],
            comparison_path,
        )
        _validate_benchmark_scorecard_delta(
            comparison["delta"],
            comparison_path,
        )
        if "statistics" in comparison:
            _validate_benchmark_scorecard_statistics(
                comparison["statistics"],
                comparison_path,
            )
        if "delivery" in comparison:
            _validate_benchmark_scorecard_delivery(
                comparison["delivery"],
                comparison_path,
            )
        vessels = _require_list(comparison["vessels"], f"{comparison_path}.vessels")
        if len(vessels) < 2:
            raise SchemaValidationError(
                f"{comparison_path}.vessels must contain at least two vessels"
            )
        for vessel_index, vessel_value in enumerate(vessels):
            vessel_path = f"{comparison_path}.vessels[{vessel_index}]"
            vessel = _require_object(vessel_value, vessel_path)
            _require_keys(
                vessel,
                (
                    "name",
                    "status",
                    "submitted_instances",
                    "resolved_instances",
                    "resolution_rate",
                ),
                vessel_path,
            )
            _require_non_empty_string(vessel.get("name"), f"{vessel_path}.name")
            _require_allowed_value(
                vessel.get("status"),
                BENCHMARK_SCORECARD_VESSEL_STATUSES,
                f"{vessel_path}.status",
            )
            for key in ("submitted_instances", "resolved_instances"):
                value = vessel.get(key)
                if not isinstance(value, int) or value < 0:
                    raise SchemaValidationError(
                        f"{vessel_path}.{key} must be an integer >= 0"
                    )
            rate = vessel.get("resolution_rate")
            if not isinstance(rate, int | float) or rate < 0:
                raise SchemaValidationError(
                    f"{vessel_path}.resolution_rate must be a number >= 0"
                )
            for key in ("resolved_ids", "unresolved_ids"):
                if key in vessel:
                    _require_string_list(vessel[key], f"{vessel_path}.{key}")
            if "task_diagnostics" in vessel:
                _validate_benchmark_scorecard_task_diagnostics(
                    vessel["task_diagnostics"],
                    f"{vessel_path}.task_diagnostics",
                )
            if vessel.get("status") == "recorded":
                _validate_benchmark_scorecard_baseline_source(
                    vessel.get("baseline_source"),
                    f"{vessel_path}.baseline_source",
                )
                continue
            _require_keys(
                vessel,
                (
                    "eligible_for_benchmark",
                    "preflight_status",
                    "preflight_reason",
                    "preflight_artifact_path",
                ),
                vessel_path,
            )
            if not isinstance(vessel.get("eligible_for_benchmark"), bool):
                raise SchemaValidationError(
                    f"{vessel_path}.eligible_for_benchmark must be a boolean"
                )
            for key in (
                "preflight_status",
                "preflight_reason",
                "preflight_artifact_path",
            ):
                _require_non_empty_string(vessel.get(key), f"{vessel_path}.{key}")
            if "preflight_error" in vessel:
                _require_non_empty_string(
                    vessel["preflight_error"],
                    f"{vessel_path}.preflight_error",
                )
        _validate_benchmark_scorecard_summary_matches_vessels(
            comparison["summary"],
            vessels,
            comparison_path,
        )
        _validate_benchmark_scorecard_delta_matches_vessels(
            comparison["delta"],
            vessels,
            comparison_path,
        )


def _validate_benchmark_scorecard_delivery(value: Any, path: str) -> None:
    delivery = _require_object(value, f"{path}.delivery")
    _require_keys(delivery, ("vessel", "status", "tools"), f"{path}.delivery")
    _require_non_empty_string(delivery.get("vessel"), f"{path}.delivery.vessel")
    _require_allowed_value(
        delivery.get("status"),
        {"delivered", "not-delivered", "unmeasured"},
        f"{path}.delivery.status",
    )
    _validate_tool_invocations(delivery.get("tools"), f"{path}.delivery.tools")


def _validate_benchmark_scorecard_baseline_source(value: Any, path: str) -> None:
    baseline_source = _require_object(value, path)
    _require_keys(baseline_source, ("logbook", "vessel"), path)
    _require_non_empty_string(baseline_source.get("logbook"), f"{path}.logbook")
    _require_non_empty_string(baseline_source.get("vessel"), f"{path}.vessel")
    if "run_date" in baseline_source:
        _require_non_empty_string(
            baseline_source["run_date"],
            f"{path}.run_date",
        )
    if "provenance" in baseline_source:
        _require_object(baseline_source["provenance"], f"{path}.provenance")
    if "usage" in baseline_source:
        usage = _require_object(baseline_source["usage"], f"{path}.usage")
        for key, usage_value in usage.items():
            if not isinstance(usage_value, int | float) or usage_value < 0:
                raise SchemaValidationError(f"{path}.usage.{key} must be a number >= 0")


def _validate_benchmark_scorecard_task_diagnostics(value: Any, path: str) -> None:
    diagnostics = _require_list(value, path)
    for index, diagnostic_value in enumerate(diagnostics):
        diagnostic_path = f"{path}[{index}]"
        diagnostic = _require_object(diagnostic_value, diagnostic_path)
        _require_keys(
            diagnostic,
            (
                "task",
                "result",
                "reason",
                "response_matched",
                "missing_response_fields",
                "mismatched_response_fields",
                "expected_tool_calls",
                "observed_tool_calls",
                "missing_tool_calls",
            ),
            diagnostic_path,
        )
        _require_non_empty_string(diagnostic.get("task"), f"{diagnostic_path}.task")
        _require_allowed_value(
            diagnostic.get("result"),
            {"resolved", "unresolved"},
            f"{diagnostic_path}.result",
        )
        _require_non_empty_string(diagnostic.get("reason"), f"{diagnostic_path}.reason")
        if not isinstance(diagnostic.get("response_matched"), bool):
            raise SchemaValidationError(
                f"{diagnostic_path}.response_matched must be a boolean"
            )
        for key in (
            "missing_response_fields",
            "mismatched_response_fields",
            "expected_tool_calls",
            "observed_tool_calls",
            "missing_tool_calls",
        ):
            _require_string_list(diagnostic.get(key), f"{diagnostic_path}.{key}")


def _validate_benchmark_scorecard_delta(value: Any, path: str) -> None:
    delta = _require_object(value, f"{path}.delta")
    _require_keys(
        delta,
        (
            "baseline_vessel",
            "challenger_vessel",
            "resolved_instances_delta",
            "resolution_rate_delta",
        ),
        f"{path}.delta",
    )
    for key in ("baseline_vessel", "challenger_vessel"):
        _require_non_empty_string(delta.get(key), f"{path}.delta.{key}")
    if not isinstance(delta.get("resolved_instances_delta"), int):
        raise SchemaValidationError(
            f"{path}.delta.resolved_instances_delta must be an integer"
        )
    if not isinstance(delta.get("resolution_rate_delta"), int | float):
        raise SchemaValidationError(
            f"{path}.delta.resolution_rate_delta must be a number"
        )


def _validate_benchmark_scorecard_delta_matches_vessels(
    delta: dict[str, Any],
    vessels: list[Any],
    path: str,
) -> None:
    baseline = vessels[0]
    challenger = vessels[1]
    expected = {
        "baseline_vessel": baseline["name"],
        "challenger_vessel": challenger["name"],
        "resolved_instances_delta": challenger["resolved_instances"]
        - baseline["resolved_instances"],
        "resolution_rate_delta": challenger["resolution_rate"]
        - baseline["resolution_rate"],
    }
    for key, expected_value in expected.items():
        if key == "resolution_rate_delta" and abs(delta[key] - expected_value) <= 1e-9:
            continue
        if delta[key] != expected_value:
            raise SchemaValidationError(
                f"{path}.delta.{key} must equal {expected_value}"
            )


def _validate_benchmark_scorecard_summary(value: Any, path: str) -> None:
    summary = _require_object(value, f"{path}.summary")
    _require_keys(
        summary,
        BENCHMARK_SCORECARD_SUMMARY_KEYS,
        f"{path}.summary",
    )
    for key in BENCHMARK_SCORECARD_SUMMARY_KEYS:
        value = summary.get(key)
        if not isinstance(value, int) or value < 0:
            raise SchemaValidationError(f"{path}.summary.{key} must be an integer >= 0")


def _validate_benchmark_scorecard_summary_matches_vessels(
    summary: dict[str, Any],
    vessels: list[Any],
    path: str,
) -> None:
    live = [vessel for vessel in vessels if vessel["status"] != "recorded"]
    expected = {
        "total_vessels": len(vessels),
        "eligible_vessels": sum(
            1 for vessel in live if vessel["eligible_for_benchmark"]
        ),
        "blocked_vessels": sum(
            1 for vessel in live if not vessel["eligible_for_benchmark"]
        ),
        "measured_vessels": sum(
            1 for vessel in vessels if vessel["status"] == "measured"
        ),
        "missing_result_vessels": sum(
            1 for vessel in vessels if vessel["status"] == "missing"
        ),
    }
    recorded = len(vessels) - len(live)
    if summary.get("recorded_vessels", 0) != recorded:
        raise SchemaValidationError(
            f"{path}.summary.recorded_vessels must equal {recorded}"
        )
    _validate_benchmark_scorecard_summary_matches_expected(
        summary,
        expected,
        f"{path}.summary",
    )


def _validate_benchmark_scorecard_top_level_summary(value: Any) -> None:
    summary = _require_object(value, "benchmark scorecard.summary")
    _require_keys(
        summary,
        ("total_comparisons", *BENCHMARK_SCORECARD_SUMMARY_KEYS),
        "benchmark scorecard.summary",
    )
    for key in ("total_comparisons", *BENCHMARK_SCORECARD_SUMMARY_KEYS):
        value = summary.get(key)
        if not isinstance(value, int) or value < 0:
            raise SchemaValidationError(
                f"benchmark scorecard.summary.{key} must be an integer >= 0"
            )


def _validate_benchmark_scorecard_top_level_summary_matches_comparisons(
    summary: dict[str, Any],
    comparisons: list[Any],
) -> None:
    expected = {
        "total_comparisons": len(comparisons),
        **{
            key: sum(comparison["summary"][key] for comparison in comparisons)
            for key in BENCHMARK_SCORECARD_SUMMARY_KEYS
        },
    }
    recorded = sum(
        comparison["summary"].get("recorded_vessels", 0) for comparison in comparisons
    )
    if summary.get("recorded_vessels", 0) != recorded:
        raise SchemaValidationError(
            f"benchmark scorecard.summary.recorded_vessels must equal {recorded}"
        )
    _validate_benchmark_scorecard_summary_matches_expected(
        summary,
        expected,
        "benchmark scorecard.summary",
    )


def _validate_benchmark_scorecard_summary_matches_expected(
    summary: dict[str, Any],
    expected: dict[str, int],
    path: str,
) -> None:
    for key, expected_value in expected.items():
        if summary[key] != expected_value:
            raise SchemaValidationError(f"{path}.{key} must equal {expected_value}")


def _validate_benchmark_execution_plan_comparisons(value: Any) -> None:
    comparisons = _require_list(value, "comparisons")
    if not comparisons:
        raise SchemaValidationError("comparisons must contain at least one comparison")
    for comparison_index, comparison_value in enumerate(comparisons):
        comparison_path = f"comparisons[{comparison_index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(
            comparison,
            ("name", "course", "status", "vessels"),
            comparison_path,
        )
        _require_non_empty_string(comparison.get("name"), f"{comparison_path}.name")
        _require_non_empty_string(comparison.get("course"), f"{comparison_path}.course")
        _require_allowed_value(
            comparison.get("status"),
            BENCHMARK_EXECUTION_PLAN_STATUSES,
            f"{comparison_path}.status",
        )
        vessels = _require_list(comparison["vessels"], f"{comparison_path}.vessels")
        if not vessels:
            raise SchemaValidationError(
                f"{comparison_path}.vessels must contain at least one vessel"
            )
        for vessel_index, vessel_value in enumerate(vessels):
            vessel_path = f"{comparison_path}.vessels[{vessel_index}]"
            vessel = _require_object(vessel_value, vessel_path)
            _require_keys(
                vessel,
                (
                    "name",
                    "status",
                    "candidate_patches_path",
                    "candidate_patches_present",
                    "grading_report_path",
                    "grading_report_present",
                    "preflight_artifact_path",
                    "preflight_artifact_present",
                    "preflight_status",
                    "runtime_instances_artifact_path",
                    "runtime_instances_artifact_present",
                    "runtime_snapshot_status",
                ),
                vessel_path,
            )
            _require_non_empty_string(vessel.get("name"), f"{vessel_path}.name")
            _require_allowed_value(
                vessel.get("status"),
                BENCHMARK_EXECUTION_PLAN_VESSEL_STATUSES,
                f"{vessel_path}.status",
            )
            for key in (
                "candidate_patches_path",
                "grading_report_path",
                "preflight_artifact_path",
                "preflight_status",
                "runtime_instances_artifact_path",
                "runtime_snapshot_status",
            ):
                _require_non_empty_string(vessel.get(key), f"{vessel_path}.{key}")
            for key in (
                "candidate_patches_present",
                "grading_report_present",
                "preflight_artifact_present",
                "runtime_instances_artifact_present",
            ):
                if not isinstance(vessel.get(key), bool):
                    raise SchemaValidationError(
                        f"{vessel_path}.{key} must be a boolean"
                    )


def _validate_benchmark_readiness_blocked_vessel(value: Any, path: str) -> None:
    vessel = _require_object(value, path)
    _require_keys(
        vessel,
        ("comparison", "vessel", "status", "details", "artifact_paths"),
        path,
    )
    for key in ("comparison", "vessel", "details"):
        _require_non_empty_string(vessel.get(key), f"{path}.{key}")
    _require_allowed_value(
        vessel.get("status"),
        BENCHMARK_READINESS_BLOCKED_VESSEL_STATUSES,
        f"{path}.status",
    )
    artifact_paths = _require_object(
        vessel["artifact_paths"],
        f"{path}.artifact_paths",
    )
    _require_keys(
        artifact_paths,
        ("candidate_patches", "preflight", "runtime_instances", "grading_report"),
        f"{path}.artifact_paths",
    )
    for key in (
        "candidate_patches",
        "preflight",
        "runtime_instances",
        "grading_report",
    ):
        _require_non_empty_string(
            artifact_paths.get(key),
            f"{path}.artifact_paths.{key}",
        )


def _validate_benchmark_launcher_handoff_comparisons(value: Any) -> None:
    comparisons = _require_list(value, "comparisons")
    if not comparisons:
        raise SchemaValidationError("comparisons must contain at least one comparison")
    for comparison_index, comparison_value in enumerate(comparisons):
        comparison_path = f"comparisons[{comparison_index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(
            comparison,
            ("name", "course", "status", "vessels"),
            comparison_path,
        )
        _require_non_empty_string(comparison.get("name"), f"{comparison_path}.name")
        _require_non_empty_string(comparison.get("course"), f"{comparison_path}.course")
        _require_allowed_value(
            comparison.get("status"),
            BENCHMARK_LAUNCHER_HANDOFF_STATUSES,
            f"{comparison_path}.status",
        )
        vessels = _require_list(comparison["vessels"], f"{comparison_path}.vessels")
        if not vessels:
            raise SchemaValidationError(
                f"{comparison_path}.vessels must contain at least one vessel"
            )
        for vessel_index, vessel_value in enumerate(vessels):
            _validate_benchmark_launcher_handoff_vessel(
                vessel_value,
                f"{comparison_path}.vessels[{vessel_index}]",
            )


def _validate_benchmark_launcher_handoff_vessel(value: Any, path: str) -> None:
    vessel = _require_object(value, path)
    _require_keys(
        vessel,
        (
            "name",
            "status",
            "candidate_patches_path",
            "candidate_patches_present",
            "expected_yacht_grading_report_path",
            "grading_report_present",
            "preflight_artifact_path",
            "preflight_artifact_present",
            "preflight_status",
            "runtime_instances_artifact_path",
            "runtime_instances_artifact_present",
            "runtime_snapshot_status",
            "native_report_dir",
            "expected_native_report_path",
        ),
        path,
    )
    _require_non_empty_string(vessel.get("name"), f"{path}.name")
    _require_allowed_value(
        vessel.get("status"),
        BENCHMARK_LAUNCHER_HANDOFF_VESSEL_STATUSES,
        f"{path}.status",
    )
    for key in (
        "candidate_patches_path",
        "expected_yacht_grading_report_path",
        "preflight_artifact_path",
        "preflight_status",
        "runtime_instances_artifact_path",
        "runtime_snapshot_status",
        "native_report_dir",
        "expected_native_report_path",
    ):
        _require_non_empty_string(vessel.get(key), f"{path}.{key}")
    for key in (
        "candidate_patches_present",
        "grading_report_present",
        "preflight_artifact_present",
        "runtime_instances_artifact_present",
    ):
        if not isinstance(vessel.get(key), bool):
            raise SchemaValidationError(f"{path}.{key} must be a boolean")
    if "command" in vessel:
        command = _require_list(vessel["command"], f"{path}.command")
        if not command or not all(isinstance(item, str) and item for item in command):
            raise SchemaValidationError(
                f"{path}.command must contain non-empty strings"
            )
    if "command_preview" in vessel:
        _require_non_empty_string(
            vessel["command_preview"],
            f"{path}.command_preview",
        )


def _validate_benchmark_launch_result_summary(value: Any) -> None:
    summary = _require_object(value, "summary")
    keys = (
        "total_vessels",
        "launched_vessels",
        "completed_launches",
        "failed_launches",
        "skipped_vessels",
    )
    _require_keys(summary, keys, "summary")
    for key in keys:
        count = summary[key]
        if not isinstance(count, int) or count < 0:
            raise SchemaValidationError(f"summary.{key} must be an integer >= 0")
    if summary["launched_vessels"] != (
        summary["completed_launches"] + summary["failed_launches"]
    ):
        raise SchemaValidationError(
            "summary.launched_vessels must equal completed_launches + failed_launches"
        )
    if summary["total_vessels"] != (
        summary["launched_vessels"] + summary["skipped_vessels"]
    ):
        raise SchemaValidationError(
            "summary.total_vessels must equal launched_vessels + skipped_vessels"
        )


def _validate_benchmark_launch_result_comparisons(value: Any) -> None:
    comparisons = _require_list(value, "comparisons")
    if not comparisons:
        raise SchemaValidationError("comparisons must contain at least one comparison")
    for comparison_index, comparison_value in enumerate(comparisons):
        comparison_path = f"comparisons[{comparison_index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(
            comparison,
            ("name", "course", "status", "vessels"),
            comparison_path,
        )
        _require_non_empty_string(comparison.get("name"), f"{comparison_path}.name")
        _require_non_empty_string(comparison.get("course"), f"{comparison_path}.course")
        _require_allowed_value(
            comparison.get("status"),
            BENCHMARK_LAUNCH_RESULT_STATUSES,
            f"{comparison_path}.status",
        )
        vessels = _require_list(comparison["vessels"], f"{comparison_path}.vessels")
        if not vessels:
            raise SchemaValidationError(
                f"{comparison_path}.vessels must contain at least one vessel"
            )
        for vessel_index, vessel_value in enumerate(vessels):
            _validate_benchmark_launch_result_vessel(
                vessel_value,
                f"{comparison_path}.vessels[{vessel_index}]",
            )


def _validate_benchmark_launch_result_vessel(value: Any, path: str) -> None:
    vessel = _require_object(value, path)
    _require_keys(vessel, ("name", "status", "launcher_status"), path)
    _require_non_empty_string(vessel.get("name"), f"{path}.name")
    _require_allowed_value(
        vessel.get("status"),
        BENCHMARK_LAUNCH_RESULT_VESSEL_STATUSES,
        f"{path}.status",
    )
    _require_allowed_value(
        vessel.get("launcher_status"),
        BENCHMARK_LAUNCHER_HANDOFF_VESSEL_STATUSES,
        f"{path}.launcher_status",
    )
    if vessel["status"] == "skipped":
        _require_non_empty_string(
            vessel.get("skipped_reason"), f"{path}.skipped_reason"
        )
        return
    _require_keys(
        vessel,
        (
            "command",
            "command_preview",
            "exit_code",
            "stdout_path",
            "stderr_path",
            "native_report_dir",
            "expected_native_report_path",
            "expected_yacht_grading_report_path",
        ),
        path,
    )
    command = _require_list(vessel["command"], f"{path}.command")
    if not command or not all(isinstance(item, str) and item for item in command):
        raise SchemaValidationError(f"{path}.command must contain non-empty strings")
    _require_non_empty_string(vessel["command_preview"], f"{path}.command_preview")
    exit_code = vessel["exit_code"]
    if not isinstance(exit_code, int) or exit_code < 0:
        raise SchemaValidationError(f"{path}.exit_code must be an integer >= 0")
    for key in (
        "stdout_path",
        "stderr_path",
        "native_report_dir",
        "expected_native_report_path",
        "expected_yacht_grading_report_path",
    ):
        _require_non_empty_string(vessel.get(key), f"{path}.{key}")


def _validate_runtime_instances_comparisons(value: Any) -> None:
    comparisons = _require_list(value, "comparisons")
    if not comparisons:
        raise SchemaValidationError("comparisons must contain at least one comparison")
    for comparison_index, comparison_value in enumerate(comparisons):
        comparison_path = f"comparisons[{comparison_index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(comparison, ("name", "course", "vessels"), comparison_path)
        _require_non_empty_string(comparison.get("name"), f"{comparison_path}.name")
        _require_non_empty_string(comparison.get("course"), f"{comparison_path}.course")
        vessels = _require_list(comparison["vessels"], f"{comparison_path}.vessels")
        if not vessels:
            raise SchemaValidationError(
                f"{comparison_path}.vessels must contain at least one vessel"
            )
        for vessel_index, vessel_value in enumerate(vessels):
            _validate_runtime_instances_vessel(
                vessel_value,
                f"{comparison_path}.vessels[{vessel_index}]",
            )


def _validate_runtime_instances_vessel(value: Any, path: str) -> None:
    vessel = _require_object(value, path)
    _require_keys(
        vessel,
        (
            "name",
            "runtime",
            "backend",
            "harness",
            "agent",
            "trial_root",
            "temp_home",
            "workspace_path",
            "command_prefix",
            "command",
            "env",
            "secret_refs",
            "cleanup_paths",
        ),
        path,
    )
    for key in (
        "name",
        "runtime",
        "backend",
        "harness",
        "agent",
        "trial_root",
        "temp_home",
        "workspace_path",
    ):
        _require_non_empty_string(vessel.get(key), f"{path}.{key}")
    for key in ("image", "container_home", "container_workspace"):
        if key in vessel:
            _require_non_empty_string(vessel.get(key), f"{path}.{key}")
    for key in ("command_prefix", "command", "cleanup_paths"):
        values = _require_list(vessel[key], f"{path}.{key}")
        if not values or not all(isinstance(item, str) and item for item in values):
            raise SchemaValidationError(f"{path}.{key} must contain non-empty strings")
    env = _require_object(vessel["env"], f"{path}.env")
    for env_key, env_value in env.items():
        _require_non_empty_string(env_key, f"{path}.env key")
        _require_non_empty_string(env_value, f"{path}.env.{env_key}")
    secret_refs = _require_list(vessel["secret_refs"], f"{path}.secret_refs")
    for secret_index, secret_value in enumerate(secret_refs):
        secret_path = f"{path}.secret_refs[{secret_index}]"
        secret = _require_object(secret_value, secret_path)
        _require_keys(secret, ("name", "source", "ref", "redacted"), secret_path)
        for key in ("name", "source", "ref"):
            _require_non_empty_string(secret.get(key), f"{secret_path}.{key}")
        if secret.get("redacted") is not True:
            raise SchemaValidationError(f"{secret_path}.redacted must be true")


def _validate_preflight_summary_checks(value: Any, path: str) -> None:
    checks = _require_list(value, f"{path}.checks")
    if not checks:
        raise SchemaValidationError(f"{path}.checks must contain at least one check")
    for check_index, check_value in enumerate(checks):
        check_path = f"{path}.checks[{check_index}]"
        check = _require_object(check_value, check_path)
        _require_keys(
            check,
            (
                "name",
                "kind",
                "origin",
                "origin_name",
                "required",
                "included",
                "status",
            ),
            check_path,
        )
        _require_non_empty_string(check.get("name"), f"{check_path}.name")
        _require_allowed_value(
            check.get("origin"),
            {"runtime", "rigging"},
            f"{check_path}.origin",
        )
        _require_non_empty_string(
            check.get("origin_name"),
            f"{check_path}.origin_name",
        )
        _require_allowed_value(
            check.get("kind"),
            PREFLIGHT_CHECK_KINDS,
            f"{check_path}.kind",
        )
        if not isinstance(check.get("required"), bool):
            raise SchemaValidationError(f"{check_path}.required must be a boolean")
        if not isinstance(check.get("included"), bool):
            raise SchemaValidationError(f"{check_path}.included must be a boolean")
        _require_allowed_value(
            check.get("status"),
            PREFLIGHT_SUMMARY_CHECK_STATUSES,
            f"{check_path}.status",
        )
        if "omitted_reason" in check:
            _require_non_empty_string(
                check["omitted_reason"],
                f"{check_path}.omitted_reason",
            )
        if "failure_reason" in check:
            _require_non_empty_string(
                check["failure_reason"],
                f"{check_path}.failure_reason",
            )


def validate_preflight_evidence_report_document(document: dict[str, Any]) -> None:
    _require_object(document, "preflight evidence report")
    _require_keys(
        document,
        ("schema", "regatta", "course", "status", "comparisons"),
        "preflight evidence report",
    )
    _require_schema(
        document,
        PREFLIGHT_EVIDENCE_REPORT_SCHEMA,
        "preflight evidence report",
    )
    for key in ("regatta", "course"):
        _require_non_empty_string(document[key], key)
    _require_allowed_value(
        document["status"],
        PREFLIGHT_EVIDENCE_REPORT_STATUSES,
        "status",
    )
    comparisons = _require_list(document["comparisons"], "comparisons")
    if not comparisons:
        raise SchemaValidationError("comparisons must contain at least one comparison")
    for comparison_index, comparison_value in enumerate(comparisons):
        comparison_path = f"comparisons[{comparison_index}]"
        comparison = _require_object(comparison_value, comparison_path)
        _require_keys(
            comparison,
            ("name", "course", "status", "vessels"),
            comparison_path,
        )
        _require_non_empty_string(comparison.get("name"), f"{comparison_path}.name")
        _require_non_empty_string(comparison.get("course"), f"{comparison_path}.course")
        _require_allowed_value(
            comparison.get("status"),
            PREFLIGHT_EVIDENCE_REPORT_STATUSES,
            f"{comparison_path}.status",
        )
        _validate_preflight_evidence_report_vessels(
            comparison["vessels"],
            comparison_path,
        )


def _validate_preflight_evidence_report_vessels(value: Any, path: str) -> None:
    vessels = _require_list(value, f"{path}.vessels")
    if not vessels:
        raise SchemaValidationError(f"{path}.vessels must contain at least one vessel")
    for vessel_index, vessel_value in enumerate(vessels):
        vessel_path = f"{path}.vessels[{vessel_index}]"
        vessel = _require_object(vessel_value, vessel_path)
        _require_keys(
            vessel,
            (
                "name",
                "status",
                "eligible_for_benchmark",
                "reason",
                "preflight_artifact_path",
                "preflight_artifact_present",
                "preflight_status",
            ),
            vessel_path,
        )
        _require_non_empty_string(vessel.get("name"), f"{vessel_path}.name")
        _require_allowed_value(
            vessel.get("status"),
            PREFLIGHT_EVIDENCE_REPORT_VESSEL_STATUSES,
            f"{vessel_path}.status",
        )
        for key in ("reason", "preflight_artifact_path", "preflight_status"):
            _require_non_empty_string(vessel.get(key), f"{vessel_path}.{key}")
        for key in ("eligible_for_benchmark", "preflight_artifact_present"):
            if not isinstance(vessel.get(key), bool):
                raise SchemaValidationError(f"{vessel_path}.{key} must be a boolean")
        if "error" in vessel:
            _require_non_empty_string(vessel["error"], f"{vessel_path}.error")


def _require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaValidationError(f"{path} must be an object")
    return value


def _require_keys(document: dict[str, Any], keys: tuple[str, ...], path: str) -> None:
    for key in keys:
        if key not in document:
            raise SchemaValidationError(f"{path}.{key} is required")


def _require_non_empty_string(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value:
        raise SchemaValidationError(f"{path} must be a non-empty string")


def _require_string(value: Any, path: str) -> None:
    if not isinstance(value, str):
        raise SchemaValidationError(f"{path} must be a string")


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise SchemaValidationError(f"{path} must be a list")
    return value


def _require_string_list(value: Any, path: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaValidationError(f"{path} must be a list of strings")


def _require_non_negative_int(value: Any, path: str) -> None:
    if not isinstance(value, int) or value < 0:
        raise SchemaValidationError(f"{path} must be an integer >= 0")


def _require_non_negative_number(value: Any, path: str) -> None:
    if not isinstance(value, int | float) or value < 0:
        raise SchemaValidationError(f"{path} must be a number >= 0")


def _require_schema(document: dict[str, Any], expected: str, path: str) -> None:
    if document.get("schema") != expected:
        raise SchemaValidationError(f"{path}.schema must be {expected}")


def _validate_redacted_secret_refs(value: Any, path: str) -> None:
    secret_refs = _require_list(value, path)
    for index, secret_ref_value in enumerate(secret_refs):
        secret_path = f"{path}[{index}]"
        secret_ref = _require_object(secret_ref_value, secret_path)
        _require_keys(secret_ref, ("name", "source", "ref", "redacted"), secret_path)
        for key in ("name", "source", "ref"):
            _require_non_empty_string(secret_ref.get(key), f"{secret_path}.{key}")
        if secret_ref.get("redacted") is not True:
            raise SchemaValidationError(f"{secret_path}.redacted must be true")


def _validate_preflight_config(document: dict[str, Any]) -> None:
    preflight = document.get("preflight", {})
    if not isinstance(preflight, dict):
        raise SchemaValidationError("preflight must be an object")
    policy = preflight.get("failure_policy", "abort-group")
    _require_allowed_value(
        policy,
        PREFLIGHT_FAILURE_POLICIES,
        "preflight.failure_policy",
    )


def _validate_course_adapter(course: dict[str, Any]) -> None:
    adapter_value = course.get("adapter")
    if adapter_value is None:
        return

    _validate_course_adapter_fields(
        _require_object(adapter_value, "course.adapter"),
        "course.adapter",
    )


_CONTEST_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_course_adapter_window(adapter: dict[str, Any], path: str) -> None:
    start_date = adapter.get("start_date")
    end_date = adapter.get("end_date")
    for key, value in (("start_date", start_date), ("end_date", end_date)):
        if value is not None and (
            not isinstance(value, str) or _CONTEST_DATE.fullmatch(value) is None
        ):
            raise SchemaValidationError(
                f"{path}.{key} must be a YYYY-MM-DD date string"
            )
    if (
        isinstance(start_date, str)
        and isinstance(end_date, str)
        and start_date > end_date
    ):
        raise SchemaValidationError(
            f"{path}.start_date must not be after {path}.end_date"
        )
    if adapter.get("kind") == "livecodebench" and (
        start_date is None or end_date is None
    ):
        raise SchemaValidationError(
            f"{path} requires start_date and end_date for the livecodebench "
            "contest-date window"
        )


def _validate_course_adapter_fields(adapter: dict[str, Any], path: str) -> None:
    _require_keys(
        adapter,
        ("kind", "dataset", "split", "harness"),
        path,
    )
    _require_allowed_value(
        adapter.get("kind"),
        COURSE_ADAPTER_KINDS,
        f"{path}.kind",
    )
    for key in ("dataset", "split"):
        _require_non_empty_string(adapter.get(key), f"{path}.{key}")
    _require_allowed_value(
        adapter.get("harness"),
        set(supported_course_adapter_harnesses(str(adapter.get("kind")))),
        f"{path}.harness",
    )
    _validate_course_adapter_window(adapter, path)
    content_digest = adapter.get("content_digest")
    if content_digest is not None:
        _require_non_empty_string(content_digest, f"{path}.content_digest")
    instance_ids = adapter.get("instance_ids")
    if instance_ids is not None:
        _validate_adapter_instance_ids(instance_ids, f"{path}.instance_ids")
    instance_file = adapter.get("instance_file")
    instance_files = adapter.get("instance_files")
    if instance_ids is not None and instance_file is not None:
        raise SchemaValidationError(
            f"{path} must not define both instance_ids and instance_file"
        )
    if instance_ids is not None and instance_files is not None:
        raise SchemaValidationError(
            f"{path} must not define both instance_ids and instance_files"
        )
    if instance_file is not None and instance_files is not None:
        raise SchemaValidationError(
            f"{path} must not define both instance_file and instance_files"
        )
    if instance_file is not None:
        _require_non_empty_string(instance_file, f"{path}.instance_file")
    if instance_files is not None:
        files = _require_list(instance_files, f"{path}.instance_files")
        if not files:
            raise SchemaValidationError(
                f"{path}.instance_files must contain at least one file"
            )
        for index, file in enumerate(files):
            _require_non_empty_string(file, f"{path}.instance_files[{index}]")
    max_instances = adapter.get("max_instances")
    if max_instances is not None:
        if not isinstance(max_instances, int) or max_instances < 1:
            raise SchemaValidationError(f"{path}.max_instances must be an integer >= 1")


def _course_adapter_selects_instances(adapter: object) -> bool:
    if not isinstance(adapter, dict):
        return False
    return any(
        key in adapter for key in ("instance_ids", "instance_file", "instance_files")
    )


def _course_adapter_instance_ids(adapter: object) -> list[str]:
    if not isinstance(adapter, dict):
        return []
    value = adapter.get("instance_ids")
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _validate_adapter_instance_ids(value: Any, path: str) -> None:
    instance_ids = _require_list(value, path)
    if not instance_ids:
        raise SchemaValidationError(f"{path} must contain at least one instance ID")
    seen = set()
    for index, instance_id in enumerate(instance_ids):
        _require_non_empty_string(instance_id, f"{path}[{index}]")
        if instance_id in seen:
            raise SchemaValidationError(f"{path}[{index}] is duplicated")
        seen.add(instance_id)


def _validate_course_adapter_summary(adapter: dict[str, Any], path: str) -> None:
    _require_keys(adapter, ("kind", "dataset", "split"), path)
    _require_allowed_value(adapter.get("kind"), COURSE_ADAPTER_KINDS, f"{path}.kind")
    for key in ("dataset", "split"):
        _require_non_empty_string(adapter.get(key), f"{path}.{key}")


def _validate_harness_declarations(document: dict[str, Any]) -> None:
    declarations = _optional_named_table(document, "harnesses")
    for name, declaration_value in declarations.items():
        path = f"harnesses.{name}"
        _require_non_empty_string(name, "harnesses key")
        if name in BUILT_IN_HARNESS_NAMES:
            raise SchemaValidationError(
                f"{path} must not shadow the built-in harness {name}"
            )
        declaration = _require_object(declaration_value, path)
        _require_allowed_value(
            declaration.get("prompt", "argument"),
            HARNESS_PROMPT_MODES,
            f"{path}.prompt",
        )
        _require_allowed_value(
            declaration.get("evidence", "stdout"),
            HARNESS_EVIDENCE_SOURCES,
            f"{path}.evidence",
        )
        if "command" in declaration:
            command = _require_list(declaration.get("command"), f"{path}.command")
            if not command or not all(
                isinstance(item, str) and item for item in command
            ):
                raise SchemaValidationError(
                    f"{path}.command must contain non-empty strings"
                )
        if "install" in declaration:
            _validate_harness_install(declaration.get("install"), f"{path}.install")
        if "evidence_map" in declaration:
            _validate_evidence_map(
                declaration.get("evidence_map"), f"{path}.evidence_map"
            )


_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def _validate_harness_install(value: Any, path: str) -> None:
    install = _require_object(value, path)
    sha256 = install.get("sha256")
    if not isinstance(sha256, str) or _SHA256_HEX.fullmatch(sha256) is None:
        raise SchemaValidationError(
            f"{path}.sha256 must be a 64-character lowercase hex digest"
        )
    has_url = "url" in install
    has_path = "path" in install
    if has_url == has_path:
        raise SchemaValidationError(f"{path} must set exactly one of url or path")
    if has_url:
        _require_non_empty_string(install.get("url"), f"{path}.url")
    if has_path:
        _require_non_empty_string(install.get("path"), f"{path}.path")


def _validate_declared_evidence_backends(document: dict[str, Any]) -> None:
    declarations = _optional_named_table(document, "harnesses")
    if not declarations:
        return
    for runtime_name, runtime_value in _optional_named_table(
        document, "runtimes"
    ).items():
        if not isinstance(runtime_value, dict):
            continue
        harness = runtime_value.get("harness")
        declaration = declarations.get(harness) if isinstance(harness, str) else None
        if not isinstance(declaration, dict):
            continue
        if (
            runtime_value.get("backend") == "container"
            and declaration.get("evidence", "stdout") == "file"
        ):
            raise SchemaValidationError(
                f"runtimes.{runtime_name} uses declared harness {harness} "
                'with evidence = "file", which does not reach container '
                "runtimes yet (the evidence path cannot cross the container "
                'boundary); use evidence = "stdout" or a host backend'
            )


_EVIDENCE_MAP_REQUIRED = ("response", "input_tokens", "output_tokens")
_EVIDENCE_MAP_ALLOWED = set(_EVIDENCE_MAP_REQUIRED) | {
    "tool_calls",
    "model",
    "cost_usd",
    "usage_reported",
}


def _validate_evidence_map(value: Any, path: str) -> None:
    mapping = _require_object(value, path)
    for key in _EVIDENCE_MAP_REQUIRED:
        _require_non_empty_string(mapping.get(key), f"{path}.{key}")
    for key, mapped in mapping.items():
        if key not in _EVIDENCE_MAP_ALLOWED:
            allowed = ", ".join(sorted(_EVIDENCE_MAP_ALLOWED))
            raise SchemaValidationError(
                f"{path}.{key} is not a mappable evidence field; allowed: {allowed}"
            )
        _require_non_empty_string(mapped, f"{path}.{key}")


def validate_harness_evidence_document(document: Any) -> None:
    evidence = _require_object(document, "harness evidence document")
    if evidence.get("schema") != HARNESS_EVIDENCE_SCHEMA:
        raise SchemaValidationError(
            f"harness evidence schema must be {HARNESS_EVIDENCE_SCHEMA}"
        )
    response = evidence.get("response")
    if not isinstance(response, str):
        raise SchemaValidationError("harness evidence response must be a string")
    usage = _require_object(evidence.get("usage"), "harness evidence usage")
    for key in ("input_tokens", "output_tokens"):
        value = usage.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise SchemaValidationError(
                f"harness evidence usage.{key} must be an integer >= 0"
            )
    reported = usage.get("reported")
    if reported is not None and not isinstance(reported, bool):
        raise SchemaValidationError("harness evidence usage.reported must be a boolean")
    for key in ("cache_read_tokens", "cache_write_tokens", "total_tokens"):
        value = usage.get(key)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise SchemaValidationError(
                f"harness evidence usage.{key} must be an integer >= 0"
            )
    tool_calls = evidence.get("tool_calls")
    if tool_calls is not None:
        entries = _require_list(tool_calls, "harness evidence tool_calls")
        for index, entry_value in enumerate(entries):
            entry_path = f"harness evidence tool_calls[{index}]"
            entry = _require_object(entry_value, entry_path)
            _require_non_empty_string(entry.get("name"), f"{entry_path}.name")
            count = entry.get("count")
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise SchemaValidationError(
                    f"{entry_path}.count must be an integer >= 1"
                )
    cost = evidence.get("cost")
    if cost is not None:
        cost_object = _require_object(cost, "harness evidence cost")
        total = cost_object.get("total_usd")
        if not isinstance(total, int | float) or isinstance(total, bool) or total < 0:
            raise SchemaValidationError(
                "harness evidence cost.total_usd must be a number >= 0"
            )
    model = evidence.get("model")
    if model is not None:
        _require_non_empty_string(model, "harness evidence model")
    extras = evidence.get("extras")
    if extras is not None:
        _require_object(extras, "harness evidence extras")


def _validate_secret_references(document: dict[str, Any]) -> set[str]:
    secrets = _optional_named_table(document, "secrets")
    for secret_name, secret_value in secrets.items():
        secret = _require_object(secret_value, f"secrets.{secret_name}")
        source = secret.get("source")
        _require_non_empty_string(source, f"secrets.{secret_name}.source")
        if source == "env":
            _require_non_empty_string(secret.get("name"), f"secrets.{secret_name}.name")
        elif source == "file":
            _require_non_empty_string(secret.get("path"), f"secrets.{secret_name}.path")
        else:
            raise SchemaValidationError(
                f"secrets.{secret_name}.source must be env or file"
            )
    return set(secrets)


def _validate_runtime_recipes(
    document: dict[str, Any],
    secrets: set[str],
) -> set[str]:
    runtimes = _optional_named_table(document, "runtimes")
    for runtime_name, runtime_value in runtimes.items():
        runtime = _require_object(runtime_value, f"runtimes.{runtime_name}")
        _require_keys(
            runtime,
            ("backend",),
            f"runtimes.{runtime_name}",
        )
        _require_non_empty_string(
            runtime["backend"], f"runtimes.{runtime_name}.backend"
        )
        _validate_runtime_backend_fields(runtime, f"runtimes.{runtime_name}")
        if "harness" in runtime:
            _require_non_empty_string(
                runtime.get("harness"),
                f"runtimes.{runtime_name}.harness",
            )
        if "harness_version" in runtime:
            _require_non_empty_string(
                runtime.get("harness_version"),
                f"runtimes.{runtime_name}.harness_version",
            )
        if "agent" in runtime:
            _require_non_empty_string(
                runtime.get("agent"),
                f"runtimes.{runtime_name}.agent",
            )
        if (
            "harness" in runtime
            and "agent" in runtime
            and runtime["harness"] != runtime["agent"]
        ):
            raise SchemaValidationError(
                f"runtimes.{runtime_name}.agent must match "
                f"runtimes.{runtime_name}.harness when both are set"
            )
        if "command" in runtime:
            command = _require_list(
                runtime["command"], f"runtimes.{runtime_name}.command"
            )
            if not command or not all(
                isinstance(item, str) and item for item in command
            ):
                raise SchemaValidationError(
                    f"runtimes.{runtime_name}.command must contain non-empty strings"
                )
        _require_string_mapping(runtime.get("env", {}), f"runtimes.{runtime_name}.env")
        _require_string_list(
            runtime.get("required_secrets", []),
            f"runtimes.{runtime_name}.required_secrets",
        )
        _require_string_list(
            runtime.get("mounts", []),
            f"runtimes.{runtime_name}.mounts",
        )
        _validate_preflight_recipe(
            runtime.get("preflight", {}),
            f"runtimes.{runtime_name}.preflight",
        )
        for secret in runtime.get("required_secrets", []):
            if secret not in secrets:
                raise SchemaValidationError(
                    f"runtimes.{runtime_name}.required_secrets references undefined "
                    f"secret {secret}"
                )
    return set(runtimes)


def _adapter_native_rollout(kind: Any) -> bool:
    if not isinstance(kind, str) or kind not in COURSE_ADAPTER_KINDS:
        return False
    from yacht.courses.registry import course_adapter

    return bool(course_adapter(kind).native_rollout)


def _validate_runtime_backend_fields(runtime: dict[str, Any], path: str) -> None:
    backend = runtime["backend"]
    if backend == "host-nix":
        if "command" not in runtime:
            raise SchemaValidationError(f"{path}.command is required")
        if "flake" not in runtime:
            raise SchemaValidationError(f"{path}.flake is required")
        _require_non_empty_string(runtime.get("flake"), f"{path}.flake")
        if "image" in runtime:
            _require_non_empty_string(runtime["image"], f"{path}.image")
    elif backend == "container":
        if "command" not in runtime:
            raise SchemaValidationError(f"{path}.command is required")
        if "image" not in runtime:
            raise SchemaValidationError(f"{path}.image is required")
        _require_non_empty_string(runtime.get("image"), f"{path}.image")
        if "flake" in runtime:
            _require_non_empty_string(runtime["flake"], f"{path}.flake")
        _require_absolute_container_path(
            runtime.get("container_home", "/home/yacht"),
            f"{path}.container_home",
        )
        _require_absolute_container_path(
            runtime.get("container_workspace", "/workspace"),
            f"{path}.container_workspace",
        )
    elif backend == "harbor":
        for key in ("command", "flake"):
            if key in runtime:
                raise SchemaValidationError(
                    f"{path}.{key} must not be set for the harbor backend; "
                    "the launcher image owns execution"
                )
        for key in ("image", "harness", "harness_version"):
            if key not in runtime:
                raise SchemaValidationError(
                    f"{path}.{key} is required for the harbor backend"
                )
        _require_non_empty_string(runtime.get("image"), f"{path}.image")
    else:
        raise SchemaValidationError(
            f"{path}.backend must be host-nix, container, or harbor"
        )


def _validate_tool_capabilities(document: dict[str, Any]) -> set[str]:
    tools = _optional_named_table(document, "tools")
    built_in_tools = set(BUILT_IN_TOOL_CAPABILITIES)
    for tool_name, tool_value in tools.items():
        tool = _require_object(tool_value, f"tools.{tool_name}")
        _require_non_empty_string(tool.get("kind"), f"tools.{tool_name}.kind")
        if "description" in tool:
            _require_string(tool.get("description"), f"tools.{tool_name}.description")
        _require_string_list(
            tool.get("interfaces", []),
            f"tools.{tool_name}.interfaces",
        )
        install_methods = tool.get("install_methods", [])
        _require_string_list(install_methods, f"tools.{tool_name}.install_methods")
        for method in install_methods:
            _require_allowed_value(
                method,
                RIGGING_INSTALL_METHODS,
                f"tools.{tool_name}.install_methods",
            )
        _require_string_list(
            tool.get("expected_tool_calls", []),
            f"tools.{tool_name}.expected_tool_calls",
        )
        provides = tool.get("provides", [])
        provides_list = _require_list(provides, f"tools.{tool_name}.provides")
        for index, entry_value in enumerate(provides_list):
            entry_path = f"tools.{tool_name}.provides[{index}]"
            entry = _require_object(entry_value, entry_path)
            _require_allowed_value(
                entry.get("method"), {"mcp-server"}, f"{entry_path}.method"
            )
            _require_non_empty_string(entry.get("harness"), f"{entry_path}.harness")
            if not supported_mcp_install_provider(tool_name, str(entry["harness"])):
                raise SchemaValidationError(
                    f"{entry_path} declares an unsupported provider: yacht "
                    f"does not ship a {entry['method']} rendering for tool "
                    f"{tool_name} on harness {entry['harness']}"
                )
    return built_in_tools | set(tools)


def _require_absolute_container_path(value: Any, path: str) -> None:
    _require_non_empty_string(value, path)
    if not str(value).startswith("/"):
        raise SchemaValidationError(f"{path} must be an absolute container path")


def _validate_rigging_recipes(
    document: dict[str, Any],
    secrets: set[str],
    tools: set[str],
) -> set[str]:
    riggings = _optional_named_table(document, "riggings")
    for rigging_name, rigging_value in riggings.items():
        rigging = _require_object(rigging_value, f"riggings.{rigging_name}")
        _require_string_list(
            rigging.get("tools", []),
            f"riggings.{rigging_name}.tools",
        )
        for tool_name in rigging.get("tools", []):
            if tool_name not in tools:
                raise SchemaValidationError(
                    f"riggings.{rigging_name}.tools references undefined tool "
                    f"{tool_name}; define [tools.{tool_name}]"
                )
        _validate_rigging_install_steps(
            rigging.get("install", []),
            f"riggings.{rigging_name}.install",
        )
        _require_string_mapping(rigging.get("env", {}), f"riggings.{rigging_name}.env")
        instructions = rigging.get("instructions", "")
        if not isinstance(instructions, str):
            raise SchemaValidationError(
                f"riggings.{rigging_name}.instructions must be a string"
            )
        _require_string_list(
            rigging.get("required_secrets", []),
            f"riggings.{rigging_name}.required_secrets",
        )
        _validate_preflight_recipe(
            rigging.get("preflight", {}),
            f"riggings.{rigging_name}.preflight",
        )
        for secret in rigging.get("required_secrets", []):
            if secret not in secrets:
                raise SchemaValidationError(
                    f"riggings.{rigging_name}.required_secrets references undefined "
                    f"secret {secret}"
                )
    return set(riggings)


def _validate_rigging_install_steps(value: Any, path: str) -> None:
    steps = _require_list(value, path)
    for index, step_value in enumerate(steps):
        step_path = f"{path}[{index}]"
        if isinstance(step_value, str):
            if not step_value:
                raise SchemaValidationError(f"{step_path} must be a non-empty string")
            continue
        step = _require_object(step_value, step_path)
        _require_keys(step, ("method", "target"), step_path)
        _require_allowed_value(
            step.get("method"),
            RIGGING_INSTALL_METHODS,
            f"{step_path}.method",
        )
        _require_non_empty_string(step.get("target"), f"{step_path}.target")
        for key in ("agent", "runtime", "package", "source"):
            if key in step:
                _require_non_empty_string(step.get(key), f"{step_path}.{key}")
        if "content" in step:
            _require_string(step.get("content"), f"{step_path}.content")
        if "command" in step:
            command = _require_list(step["command"], f"{step_path}.command")
            if not command or not all(
                isinstance(item, str) and item for item in command
            ):
                raise SchemaValidationError(
                    f"{step_path}.command must contain non-empty strings"
                )


def _validate_preflight_recipe(value: Any, path: str) -> None:
    preflight = _require_object(value, path)
    required = preflight.get("required", True)
    if not isinstance(required, bool):
        raise SchemaValidationError(f"{path}.required must be a boolean")
    checks = _require_list(preflight.get("checks", []), f"{path}.checks")
    for index, check_value in enumerate(checks):
        check_path = f"{path}.checks[{index}]"
        check = _require_object(check_value, check_path)
        _require_non_empty_string(check.get("name"), f"{check_path}.name")
        kind = check.get("kind")
        _require_allowed_value(kind, PREFLIGHT_CHECK_KINDS, f"{check_path}.kind")
        required_check = check.get("required", True)
        if not isinstance(required_check, bool):
            raise SchemaValidationError(f"{check_path}.required must be a boolean")
        if kind == "command":
            command = _require_list(check.get("command", []), f"{check_path}.command")
            if not command or not all(
                isinstance(item, str) and item for item in command
            ):
                raise SchemaValidationError(
                    f"{check_path}.command must contain non-empty strings"
                )
        if kind in {"env", "path-isolation"}:
            env = check.get("env")
            _require_string_list(env, f"{check_path}.env")
            if not env:
                raise SchemaValidationError(
                    f"{check_path}.env must contain at least one env var"
                )
        if kind == "agent-prompt":
            _require_non_empty_string(check.get("prompt"), f"{check_path}.prompt")
            _require_string_list(
                check.get("expect_tool_calls", []),
                f"{check_path}.expect_tool_calls",
            )
            _require_string_list(
                check.get("expect_response_contains", []),
                f"{check_path}.expect_response_contains",
            )
        if kind == "tool-call":
            tool_calls = check.get("expect_tool_calls")
            _require_string_list(tool_calls, f"{check_path}.expect_tool_calls")
            if not tool_calls:
                raise SchemaValidationError(
                    f"{check_path}.expect_tool_calls must contain at least one tool"
                )


def _validate_comparisons(
    document: dict[str, Any],
    course_name: str,
    vessel_names: set[str],
) -> None:
    comparisons = document.get("comparisons", [])
    if not isinstance(comparisons, list):
        raise SchemaValidationError("comparisons must be a list")
    for index, comparison_value in enumerate(comparisons):
        comparison = _require_object(comparison_value, f"comparisons[{index}]")
        _require_non_empty_string(comparison.get("name"), f"comparisons[{index}].name")
        comparison_course = comparison.get("course", course_name)
        _require_non_empty_string(comparison_course, f"comparisons[{index}].course")
        if comparison_course != course_name:
            raise SchemaValidationError(
                f"comparisons[{index}].course must match course.name {course_name}"
            )
        vessels = _require_list(
            comparison.get("vessels"),
            f"comparisons[{index}].vessels",
        )
        baseline = comparison.get("baseline")
        if baseline is None:
            if len(vessels) < 2:
                raise SchemaValidationError(
                    f"comparisons[{index}].vessels must contain at least two "
                    "vessels; to compare one live vessel against a stored "
                    "run, reference it with comparisons.baseline"
                )
        else:
            if len(vessels) != 1:
                raise SchemaValidationError(
                    f"comparisons[{index}].vessels must contain exactly one "
                    "live vessel when comparisons.baseline is set"
                )
        for vessel in vessels:
            _require_non_empty_string(vessel, f"comparisons[{index}].vessels")
            if vessel not in vessel_names:
                raise SchemaValidationError(
                    f"comparisons[{index}].vessels references undefined vessel {vessel}"
                )
        if baseline is not None:
            _validate_comparison_baseline(
                baseline,
                vessels,
                vessel_names,
                f"comparisons[{index}].baseline",
            )


def _validate_comparison_baseline(
    baseline: Any,
    vessels: list[Any],
    vessel_names: set[str],
    path: str,
) -> None:
    baseline_object = _require_object(baseline, path)
    _require_keys(baseline_object, ("logbook", "vessel"), path)
    _require_non_empty_string(baseline_object.get("logbook"), f"{path}.logbook")
    baseline_vessel = baseline_object.get("vessel")
    _require_non_empty_string(baseline_vessel, f"{path}.vessel")
    if baseline_vessel not in vessel_names:
        raise SchemaValidationError(
            f"{path}.vessel references undefined vessel {baseline_vessel}; "
            "the baseline vessel must be declared so its recorded provenance "
            "can be checked against the config"
        )
    if baseline_vessel in vessels:
        raise SchemaValidationError(
            f"{path}.vessel must differ from the live vessel; declare the "
            "recorded configuration under its own vessel name"
        )


def _optional_named_table(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key, {})
    if not isinstance(value, dict):
        raise SchemaValidationError(f"{key} must be an object")
    for name in value:
        if not isinstance(name, str) or not name:
            raise SchemaValidationError(f"{key} names must be non-empty strings")
    return value


def _require_string_mapping(value: Any, path: str) -> None:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise SchemaValidationError(f"{path} must be an object with string values")


def _require_allowed_value(value: Any, allowed: set[str], path: str) -> None:
    if not isinstance(value, str) or value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise SchemaValidationError(f"{path} must be one of: {allowed_values}")
