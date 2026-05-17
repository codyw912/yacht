from __future__ import annotations

from typing import Any


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

PREFLIGHT_FAILURE_POLICIES = {"abort-group", "skip-vessel", "abort-regatta", "warn"}
COURSE_ADAPTER_KINDS = {"swe-bench"}
COURSE_ADAPTER_HARNESSES = {"docker"}
PREFLIGHT_CHECK_KINDS = {
    "agent-prompt",
    "artifact",
    "command",
    "env",
    "mcp-server",
    "path-isolation",
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
}
BENCHMARK_SCORECARD_STATUSES = {"complete", "partial", "empty"}
BENCHMARK_SCORECARD_VESSEL_STATUSES = {"measured", "missing"}
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
    runtime_names = _validate_runtime_recipes(document, secrets)
    rigging_names = _validate_rigging_recipes(document, secrets)

    regatta = _require_object(document["regatta"], "regatta")
    _require_non_empty_string(regatta.get("name"), "regatta.name")

    course = _require_object(document["course"], "course")
    _require_non_empty_string(course.get("name"), "course.name")
    course_name = course["name"]
    tasks = _require_list(course.get("tasks"), "course.tasks")
    if not tasks:
        raise SchemaValidationError("course.tasks must contain at least one task")
    for index, task_value in enumerate(tasks):
        task = _require_object(task_value, f"course.tasks[{index}]")
        _require_non_empty_string(task.get("id"), f"course.tasks[{index}].id")
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
    _validate_course_adapter(course)

    vessels = _require_list(document["vessels"], "vessels")
    if not vessels:
        raise SchemaValidationError("vessels must contain at least one vessel")
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
            _require_non_empty_string(secret_ref.get(key), f"secret_refs[{index}].{key}")
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
    _validate_task_attempt_runtime_context(document["runtime_context"])
    _validate_task_attempt_agent(document["agent"])
    _validate_task_attempt_metrics(document["metrics"])
    _validate_redacted_secret_refs(document["secret_refs"], "secret_refs")


def validate_task_attempt_scorecard_document(document: dict[str, Any]) -> None:
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
    _require_allowed_value(document["status"], SMOKE_READINESS_REPORT_STATUSES, "status")
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
            "tool_call_counts",
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
    _validate_tool_call_counts(vessel["tool_call_counts"], f"{path}.tool_call_counts")
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
            "tool_call_count",
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
        "tool_call_count",
        "total_tokens",
    ):
        _require_non_negative_int(vessel.get(key), f"{path}.{key}")
    _require_non_negative_number(vessel.get("success_rate"), f"{path}.success_rate")
    _require_non_negative_number(
        vessel.get("total_duration_seconds"),
        f"{path}.total_duration_seconds",
    )
    if "total_cost" in vessel:
        _require_non_negative_number(vessel.get("total_cost"), f"{path}.total_cost")
    if "tool_call_counts" in vessel:
        _validate_tool_call_counts(
            vessel.get("tool_call_counts"),
            f"{path}.tool_call_counts",
        )
    _require_string_list(vessel.get("artifact_paths"), f"{path}.artifact_paths")


def _validate_task_attempt_scorecard_summary(value: Any, path: str) -> None:
    summary = _require_object(value, path)
    for key in (
        "total_vessels",
        "total_attempts",
        "completed_attempts",
        "failed_attempts",
        "total_tool_calls",
        "total_tokens",
    ):
        _require_non_negative_int(summary.get(key), f"{path}.{key}")
    _require_non_negative_number(
        summary.get("total_duration_seconds"),
        f"{path}.total_duration_seconds",
    )
    if "total_cost" in summary:
        _require_non_negative_number(summary.get("total_cost"), f"{path}.total_cost")
    if "tool_call_counts" in summary:
        _validate_tool_call_counts(
            summary.get("tool_call_counts"),
            f"{path}.tool_call_counts",
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
    _require_string_list(
        context.get("command_prefix"),
        "runtime_context.command_prefix",
    )
    _require_string_list(context.get("command"), "runtime_context.command")
    _require_string_list(
        context.get("cleanup_paths"),
        "runtime_context.cleanup_paths",
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


def _validate_course_handoff_comparisons(value: Any) -> None:
    comparisons = _require_list(value, "comparisons")
    if not comparisons:
        raise SchemaValidationError("comparisons must contain at least one comparison")
    for index, comparison_value in enumerate(comparisons):
        comparison = _require_object(comparison_value, f"comparisons[{index}]")
        _require_keys(comparison, ("name", "course", "vessels"), f"comparisons[{index}]")
        _require_non_empty_string(comparison.get("name"), f"comparisons[{index}].name")
        _require_non_empty_string(
            comparison.get("course"),
            f"comparisons[{index}].course",
        )
        vessels = _require_list(
            comparison.get("vessels"),
            f"comparisons[{index}].vessels",
        )
        if len(vessels) < 2:
            raise SchemaValidationError(
                f"comparisons[{index}].vessels must contain at least two vessels"
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
        {"docker-harness"},
        "grading.execution",
    )
    _require_allowed_value(grading.get("status"), {"planned"}, "grading.status")


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
                    "eligible_for_benchmark",
                    "preflight_status",
                    "preflight_reason",
                    "preflight_artifact_path",
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
        if (
            key == "resolution_rate_delta"
            and abs(delta[key] - expected_value) <= 1e-9
        ):
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
            raise SchemaValidationError(
                f"{path}.summary.{key} must be an integer >= 0"
            )


def _validate_benchmark_scorecard_summary_matches_vessels(
    summary: dict[str, Any],
    vessels: list[Any],
    path: str,
) -> None:
    expected = {
        "total_vessels": len(vessels),
        "eligible_vessels": sum(
            1 for vessel in vessels if vessel["eligible_for_benchmark"]
        ),
        "blocked_vessels": sum(
            1 for vessel in vessels if not vessel["eligible_for_benchmark"]
        ),
        "measured_vessels": sum(
            1 for vessel in vessels if vessel["status"] == "measured"
        ),
        "missing_result_vessels": sum(
            1 for vessel in vessels if vessel["status"] == "missing"
        ),
    }
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
            raise SchemaValidationError(
                f"{path}.{key} must equal {expected_value}"
            )


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
            raise SchemaValidationError(f"{path}.command must contain non-empty strings")
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
            "summary.launched_vessels must equal completed_launches + "
            "failed_launches"
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
        _require_non_empty_string(vessel.get("skipped_reason"), f"{path}.skipped_reason")
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
        COURSE_ADAPTER_HARNESSES,
        f"{path}.harness",
    )


def _validate_course_adapter_summary(adapter: dict[str, Any], path: str) -> None:
    _require_keys(adapter, ("kind", "dataset", "split"), path)
    _require_allowed_value(adapter.get("kind"), COURSE_ADAPTER_KINDS, f"{path}.kind")
    for key in ("dataset", "split"):
        _require_non_empty_string(adapter.get(key), f"{path}.{key}")


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
            ("backend", "command"),
            f"runtimes.{runtime_name}",
        )
        _require_non_empty_string(runtime["backend"], f"runtimes.{runtime_name}.backend")
        _validate_runtime_backend_fields(runtime, f"runtimes.{runtime_name}")
        command = _require_list(runtime["command"], f"runtimes.{runtime_name}.command")
        if not command or not all(isinstance(item, str) and item for item in command):
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


def _validate_runtime_backend_fields(runtime: dict[str, Any], path: str) -> None:
    backend = runtime["backend"]
    if backend == "host-nix":
        if "flake" not in runtime:
            raise SchemaValidationError(f"{path}.flake is required")
        _require_non_empty_string(runtime.get("flake"), f"{path}.flake")
        if "image" in runtime:
            _require_non_empty_string(runtime["image"], f"{path}.image")
    elif backend == "container":
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
    else:
        raise SchemaValidationError(f"{path}.backend must be host-nix or container")


def _require_absolute_container_path(value: Any, path: str) -> None:
    _require_non_empty_string(value, path)
    if not str(value).startswith("/"):
        raise SchemaValidationError(f"{path} must be an absolute container path")


def _validate_rigging_recipes(
    document: dict[str, Any],
    secrets: set[str],
) -> set[str]:
    riggings = _optional_named_table(document, "riggings")
    for rigging_name, rigging_value in riggings.items():
        rigging = _require_object(rigging_value, f"riggings.{rigging_name}")
        _require_string_list(
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
            if not command or not all(isinstance(item, str) and item for item in command):
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
        if len(vessels) < 2:
            raise SchemaValidationError(
                f"comparisons[{index}].vessels must contain at least two vessels"
            )
        for vessel in vessels:
            _require_non_empty_string(vessel, f"comparisons[{index}].vessels")
            if vessel not in vessel_names:
                raise SchemaValidationError(
                    f"comparisons[{index}].vessels references undefined vessel {vessel}"
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
        isinstance(key, str) and isinstance(item, str)
        for key, item in value.items()
    ):
        raise SchemaValidationError(f"{path} must be an object with string values")


def _require_allowed_value(value: Any, allowed: set[str], path: str) -> None:
    if not isinstance(value, str) or value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise SchemaValidationError(f"{path} must be one of: {allowed_values}")
