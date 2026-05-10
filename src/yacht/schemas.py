from __future__ import annotations

from typing import Any


REGATTA_SCHEMA = "yacht.regatta.v1"
WAKE_SCHEMA = "yacht.wake.v1"
SCORECARD_SCHEMA = "yacht.scorecard.v1"
PREFLIGHT_SCHEMA = "yacht.preflight.v1"
PREFLIGHT_SUMMARY_SCHEMA = "yacht.preflight-summary.v1"

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
            "status",
            "failure_policy",
            "checks",
            "secret_refs",
        ),
        "preflight",
    )
    _require_schema(document, PREFLIGHT_SCHEMA, "preflight")
    for key in ("regatta", "vessel", "failure_policy"):
        _require_non_empty_string(document[key], key)
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
    for key in ("comparison", "runtime"):
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
            ("name", "kind", "required", "status", "evidence"),
            f"checks[{index}]",
        )
        _require_non_empty_string(check.get("name"), f"checks[{index}].name")
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
            _require_keys(vessel, ("name", "status", "checks"), vessel_path)
            _require_non_empty_string(vessel.get("name"), f"{vessel_path}.name")
            _require_allowed_value(
                vessel.get("status"),
                PREFLIGHT_STATUSES,
                f"{vessel_path}.status",
            )
            _validate_preflight_summary_checks(vessel["checks"], vessel_path)


def _validate_preflight_summary_checks(value: Any, path: str) -> None:
    checks = _require_list(value, f"{path}.checks")
    if not checks:
        raise SchemaValidationError(f"{path}.checks must contain at least one check")
    for check_index, check_value in enumerate(checks):
        check_path = f"{path}.checks[{check_index}]"
        check = _require_object(check_value, check_path)
        _require_keys(
            check,
            ("name", "kind", "required", "included", "status"),
            check_path,
        )
        _require_non_empty_string(check.get("name"), f"{check_path}.name")
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


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise SchemaValidationError(f"{path} must be a list")
    return value


def _require_string_list(value: Any, path: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaValidationError(f"{path} must be a list of strings")


def _require_schema(document: dict[str, Any], expected: str, path: str) -> None:
    if document.get("schema") != expected:
        raise SchemaValidationError(f"{path}.schema must be {expected}")


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

    adapter = _require_object(adapter_value, "course.adapter")
    _require_keys(
        adapter,
        ("kind", "dataset", "split", "harness"),
        "course.adapter",
    )
    _require_allowed_value(
        adapter.get("kind"),
        COURSE_ADAPTER_KINDS,
        "course.adapter.kind",
    )
    for key in ("dataset", "split"):
        _require_non_empty_string(adapter.get(key), f"course.adapter.{key}")
    _require_allowed_value(
        adapter.get("harness"),
        COURSE_ADAPTER_HARNESSES,
        "course.adapter.harness",
    )


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
            ("backend", "flake", "command"),
            f"runtimes.{runtime_name}",
        )
        _require_non_empty_string(runtime["backend"], f"runtimes.{runtime_name}.backend")
        _require_non_empty_string(runtime["flake"], f"runtimes.{runtime_name}.flake")
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
