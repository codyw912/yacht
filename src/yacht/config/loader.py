from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from yacht.domain.model import (
    Comparison,
    ConfigError,
    Course,
    CourseAdapter,
    ExpectationValue,
    HarnessDeclaration,
    HarnessInstall,
    PreflightCheck,
    PreflightConfig,
    PreflightRecipe,
    Regatta,
    RiggingInstallStep,
    RiggingRecipe,
    RuntimeRecipe,
    SecretReference,
    Task,
    Vessel,
)
from yacht.contracts.schemas import SchemaValidationError, validate_regatta_document
from yacht.runtimes.tool_capabilities import BUILT_IN_TOOL_CAPABILITIES, ToolCapability


def load_regatta(config_path: Path) -> Regatta:
    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)
    try:
        validate_regatta_document(raw)
    except SchemaValidationError as error:
        raise ConfigError(str(error)) from error
    raw = _expand_course_task_file(raw, config_path.parent)
    raw = _expand_course_adapter_instance_files(raw, config_path.parent)
    try:
        validate_regatta_document(raw)
    except SchemaValidationError as error:
        raise ConfigError(str(error)) from error
    raw = _limit_course_adapter_instances(raw)
    try:
        validate_regatta_document(raw)
    except SchemaValidationError as error:
        raise ConfigError(str(error)) from error

    adapter = _parse_course_adapter(raw["course"], config_path.parent)
    course = Course(
        name=str(raw["course"]["name"]),
        tasks=_parse_course_tasks(raw["course"], adapter),
        adapter=adapter,
    )
    vessels = tuple(
        Vessel(
            name=str(vessel["name"]),
            model=str(vessel["model"]),
            rigging=tuple(str(item) for item in vessel.get("rigging", ())),
            runtime=str(vessel["runtime"]) if "runtime" in vessel else None,
        )
        for vessel in raw["vessels"]
    )
    comparisons = _parse_comparisons(raw, course.name)
    _validate_artifact_path_names(course, vessels, comparisons)
    return Regatta(
        name=str(raw["regatta"]["name"]),
        course=course,
        vessels=vessels,
        preflight=_parse_preflight_config(raw),
        comparisons=comparisons,
        secrets=_parse_secrets(raw),
        runtime_recipes=_parse_runtime_recipes(raw),
        rigging_recipes=_parse_rigging_recipes(raw, config_path.parent),
        tool_capabilities=_parse_tool_capabilities(raw),
        harness_declarations=_parse_harness_declarations(raw, config_path.parent),
    )


def _parse_harness_declarations(
    raw: dict[str, Any],
    config_dir: Path,
) -> dict[str, HarnessDeclaration]:
    return {
        str(name): HarnessDeclaration(
            name=str(name),
            prompt=str(declaration.get("prompt", "argument")),
            evidence=str(declaration.get("evidence", "stdout")),
            command=tuple(str(item) for item in declaration.get("command", ())),
            install=_parse_harness_install(declaration, config_dir),
        )
        for name, declaration in raw.get("harnesses", {}).items()
    }


def _parse_harness_install(
    declaration: dict[str, Any],
    config_dir: Path,
) -> HarnessInstall | None:
    install = declaration.get("install")
    if not isinstance(install, dict):
        return None
    path = install.get("path")
    if path is not None:
        resolved = Path(str(path))
        if not resolved.is_absolute():
            resolved = config_dir / resolved
        path = str(resolved.resolve())
    return HarnessInstall(
        sha256=str(install["sha256"]),
        url=str(install["url"]) if "url" in install else None,
        path=path,
    )


_ARTIFACT_PATH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _validate_artifact_path_names(
    course: Course,
    vessels: tuple[Vessel, ...],
    comparisons: tuple[Comparison, ...],
) -> None:
    for task in course.tasks:
        _validate_artifact_path_name("course task id", task.id)
    for vessel in vessels:
        _validate_artifact_path_name("vessel name", vessel.name)
    for comparison in comparisons:
        _validate_artifact_path_name("comparison name", comparison.name)


def _validate_artifact_path_name(field: str, value: str) -> None:
    if not _ARTIFACT_PATH_NAME.match(value):
        raise ConfigError(
            f"{field} {value!r} is used in logbook paths and must start with "
            "a letter or digit and contain only letters, digits, dots, "
            "underscores, or hyphens"
        )


def _expand_course_task_file(
    raw: dict[str, Any],
    config_dir: Path,
) -> dict[str, Any]:
    course = raw.get("course")
    if not isinstance(course, dict) or (
        "task_file" not in course and "task_files" not in course
    ):
        return raw

    task_files: list[str] = []
    task_file = course.get("task_file")
    if isinstance(task_file, str):
        task_files.append(task_file)
    raw_task_files = course.get("task_files")
    if isinstance(raw_task_files, list):
        task_files.extend(
            task_file for task_file in raw_task_files if isinstance(task_file, str)
        )
    if not task_files:
        return raw

    tasks: list[Any] = []
    for task_file_path in task_files:
        tasks.extend(_load_course_task_file(task_file_path, config_dir))

    expanded = dict(raw)
    expanded_course = dict(course)
    expanded_course.pop("task_file", None)
    expanded_course.pop("task_files", None)
    expanded_course["tasks"] = tasks
    expanded["course"] = expanded_course
    return expanded


def _load_course_task_file(task_file: str, config_dir: Path) -> list[Any]:
    task_path = Path(task_file)
    if not task_path.is_absolute():
        task_path = config_dir / task_path
    try:
        with task_path.open("rb") as file:
            task_document = tomllib.load(file)
    except FileNotFoundError as error:
        raise ConfigError(f"course.task_file not found: {task_path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"course.task_file is not valid TOML: {error}") from error

    tasks = task_document.get("tasks")
    if not isinstance(tasks, list):
        raise ConfigError("course.task_file must contain tasks")
    return tasks


def _expand_course_adapter_instance_files(
    raw: dict[str, Any],
    config_dir: Path,
) -> dict[str, Any]:
    course = raw.get("course")
    if not isinstance(course, dict):
        return raw
    adapter = course.get("adapter")
    if not isinstance(adapter, dict) or (
        "instance_file" not in adapter and "instance_files" not in adapter
    ):
        return raw

    instance_files: list[str] = []
    instance_file = adapter.get("instance_file")
    if isinstance(instance_file, str):
        instance_files.append(instance_file)
    raw_instance_files = adapter.get("instance_files")
    if isinstance(raw_instance_files, list):
        instance_files.extend(
            file for file in raw_instance_files if isinstance(file, str)
        )
    if not instance_files:
        return raw

    instance_ids: list[str] = []
    for instance_file_path in instance_files:
        instance_ids.extend(
            _load_course_adapter_instance_file(instance_file_path, config_dir)
        )

    expanded = dict(raw)
    expanded_course = dict(course)
    expanded_adapter = dict(adapter)
    expanded_adapter.pop("instance_file", None)
    expanded_adapter.pop("instance_files", None)
    expanded_adapter["instance_ids"] = instance_ids
    expanded_course["adapter"] = expanded_adapter
    expanded["course"] = expanded_course
    return expanded


def _load_course_adapter_instance_file(
    instance_file: str,
    config_dir: Path,
) -> list[Any]:
    instance_path = Path(instance_file)
    if not instance_path.is_absolute():
        instance_path = config_dir / instance_path
    try:
        with instance_path.open("rb") as file:
            instance_document = tomllib.load(file)
    except FileNotFoundError as error:
        raise ConfigError(
            f"course.adapter.instance_file not found: {instance_path}"
        ) from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(
            f"course.adapter.instance_file is not valid TOML: {error}"
        ) from error

    instance_ids = instance_document.get("instance_ids")
    if not isinstance(instance_ids, list):
        raise ConfigError("course.adapter.instance_file must contain instance_ids")
    return instance_ids


def _limit_course_adapter_instances(raw: dict[str, Any]) -> dict[str, Any]:
    course = raw.get("course")
    if not isinstance(course, dict):
        return raw
    adapter = course.get("adapter")
    if not isinstance(adapter, dict) or "max_instances" not in adapter:
        return raw

    max_instances = adapter.get("max_instances")
    if not isinstance(max_instances, int) or max_instances < 1:
        return raw

    expanded = dict(raw)
    expanded_course = dict(course)
    expanded_adapter = dict(adapter)
    raw_instance_ids = adapter.get("instance_ids")
    if isinstance(raw_instance_ids, list):
        instance_ids = raw_instance_ids[:max_instances]
        expanded_adapter["instance_ids"] = instance_ids
        if isinstance(course.get("tasks"), list):
            selected_ids = set(instance_ids)
            expanded_course["tasks"] = [
                task
                for task in course["tasks"]
                if isinstance(task, dict) and task.get("id") in selected_ids
            ]
    elif isinstance(course.get("tasks"), list):
        expanded_course["tasks"] = course["tasks"][:max_instances]

    expanded_course["adapter"] = expanded_adapter
    expanded["course"] = expanded_course
    return expanded


def _parse_preflight_config(raw: dict[str, Any]) -> PreflightConfig:
    preflight = raw.get("preflight", {})
    return PreflightConfig(
        failure_policy=str(preflight.get("failure_policy", "abort-group")),
    )


def _parse_course_adapter(
    raw_course: dict[str, Any],
    config_dir: Path,
) -> CourseAdapter | None:
    if "adapter" not in raw_course:
        return None

    adapter = raw_course["adapter"]
    return CourseAdapter(
        kind=str(adapter["kind"]),
        dataset=_adapter_dataset(adapter, config_dir),
        split=str(adapter["split"]),
        harness=str(adapter["harness"]),
        instance_ids=tuple(str(item) for item in adapter.get("instance_ids", ())),
        start_date=(str(adapter["start_date"]) if "start_date" in adapter else None),
        end_date=str(adapter["end_date"]) if "end_date" in adapter else None,
    )


def _adapter_dataset(adapter: dict[str, Any], config_dir: Path) -> str:
    dataset = str(adapter["dataset"])
    if str(adapter.get("kind")) != "custom-eval":
        return dataset
    path = Path(dataset)
    if not path.is_absolute():
        path = config_dir / path
    return str(path.resolve())


def _parse_course_tasks(
    raw_course: dict[str, Any],
    adapter: CourseAdapter | None,
) -> tuple[Task, ...]:
    tasks = tuple(_parse_course_task(task) for task in raw_course.get("tasks", ()))
    if adapter is None or not adapter.instance_ids:
        return tasks

    tasks_by_id = {task.id: task for task in tasks}
    return tuple(
        tasks_by_id.get(instance_id) or _default_adapter_task(adapter, instance_id)
        for instance_id in adapter.instance_ids
    )


def _default_adapter_task(adapter: CourseAdapter, instance_id: str) -> Task:
    if adapter.kind == "swe-bench":
        return _default_swe_bench_task(instance_id)
    return Task(
        id=instance_id,
        title=f"{adapter.kind} instance {instance_id}",
        difficulty=1,
    )


def _parse_course_task(task: dict[str, Any]) -> Task:
    return Task(
        id=str(task["id"]),
        title=str(task["title"]),
        difficulty=int(task.get("difficulty", 1)),
        repo=str(task["repo"]) if "repo" in task else None,
        repo_url=str(task["repo_url"]) if "repo_url" in task else None,
        base_commit=str(task["base_commit"]) if "base_commit" in task else None,
        problem_statement=(
            str(task["problem_statement"]) if "problem_statement" in task else None
        ),
        expect_response=_parse_expect_response(task.get("expect_response", {})),
        expect_tool_calls=tuple(
            str(tool_call) for tool_call in task.get("expect_tool_calls", [])
        ),
    )


def _parse_expect_response(raw: Any) -> dict[str, ExpectationValue]:
    return {str(key): value for key, value in raw.items()}


def _default_swe_bench_task(instance_id: str) -> Task:
    return Task(
        id=instance_id,
        title=f"SWE-bench instance {instance_id}",
        difficulty=1,
    )


def _parse_comparisons(raw: dict[str, Any], course_name: str) -> tuple[Comparison, ...]:
    return tuple(
        Comparison(
            name=str(comparison["name"]),
            course=str(comparison.get("course", course_name)),
            vessels=tuple(str(item) for item in comparison["vessels"]),
        )
        for comparison in raw.get("comparisons", ())
    )


def _parse_secrets(raw: dict[str, Any]) -> dict[str, SecretReference]:
    return {
        str(name): SecretReference(
            source=str(secret["source"]),
            name=str(secret["name"]) if "name" in secret else None,
            path=str(secret["path"]) if "path" in secret else None,
        )
        for name, secret in raw.get("secrets", {}).items()
    }


def _parse_runtime_recipes(raw: dict[str, Any]) -> dict[str, RuntimeRecipe]:
    return {
        str(name): RuntimeRecipe(
            name=str(name),
            backend=str(runtime["backend"]),
            command=tuple(str(item) for item in runtime.get("command", ())),
            harness=_parse_runtime_harness(runtime),
            harness_version=(
                str(runtime["harness_version"])
                if "harness_version" in runtime
                else None
            ),
            agent=str(runtime["agent"]) if "agent" in runtime else None,
            flake=str(runtime["flake"]) if "flake" in runtime else None,
            image=str(runtime["image"]) if "image" in runtime else None,
            container_home=str(runtime.get("container_home", "/home/yacht")),
            container_workspace=str(runtime.get("container_workspace", "/workspace")),
            env={str(key): str(value) for key, value in runtime.get("env", {}).items()},
            required_secrets=tuple(
                str(item) for item in runtime.get("required_secrets", ())
            ),
            mounts=tuple(str(item) for item in runtime.get("mounts", ())),
            preflight=_parse_preflight_recipe(runtime.get("preflight", {})),
        )
        for name, runtime in raw.get("runtimes", {}).items()
    }


def _parse_runtime_harness(runtime: dict[str, Any]) -> str | None:
    if "harness" in runtime:
        return str(runtime["harness"])
    if "agent" in runtime:
        return str(runtime["agent"])
    return None


def _parse_rigging_recipes(
    raw: dict[str, Any],
    config_dir: Path,
) -> dict[str, RiggingRecipe]:
    return {
        str(name): RiggingRecipe(
            name=str(name),
            tools=tuple(str(item) for item in rigging.get("tools", ())),
            install=tuple(
                _parse_rigging_install_step(item, config_dir)
                for item in rigging.get("install", ())
            ),
            env={str(key): str(value) for key, value in rigging.get("env", {}).items()},
            required_secrets=tuple(
                str(item) for item in rigging.get("required_secrets", ())
            ),
            instructions=str(rigging.get("instructions", "")),
            preflight=_parse_preflight_recipe(rigging.get("preflight", {})),
        )
        for name, rigging in raw.get("riggings", {}).items()
    }


def _parse_tool_capabilities(raw: dict[str, Any]) -> dict[str, ToolCapability]:
    capabilities = dict(BUILT_IN_TOOL_CAPABILITIES)
    capabilities.update(
        {
            str(name): ToolCapability(
                name=str(name),
                kind=str(tool["kind"]),
                description=str(tool.get("description", "")),
                interfaces=tuple(str(item) for item in tool.get("interfaces", ())),
                install_methods=tuple(
                    str(item) for item in tool.get("install_methods", ())
                ),
                expected_tool_calls=tuple(
                    str(item) for item in tool.get("expected_tool_calls", ())
                ),
            )
            for name, tool in raw.get("tools", {}).items()
        }
    )
    return capabilities


def _parse_rigging_install_step(raw: Any, config_dir: Path) -> RiggingInstallStep:
    if isinstance(raw, str):
        return RiggingInstallStep(
            method="agent-extension",
            target=raw,
            legacy=True,
        )
    step = raw
    method = str(step["method"])
    return RiggingInstallStep(
        method=method,
        target=str(step["target"]),
        agent=str(step["agent"]) if "agent" in step else None,
        runtime=str(step["runtime"]) if "runtime" in step else None,
        package=str(step["package"]) if "package" in step else None,
        source=str(step["source"]) if "source" in step else None,
        command=tuple(str(item) for item in step.get("command", ())),
        content=_parse_install_content(step, method, config_dir),
    )


def _parse_install_content(
    step: dict[str, Any],
    method: str,
    config_dir: Path,
) -> str | None:
    content = str(step["content"]) if "content" in step else None
    if method != "config-file":
        return content
    if content is not None and "source" in step:
        raise ConfigError("config-file install must not define both content and source")
    if content is not None:
        return content
    if "source" not in step:
        raise ConfigError("config-file install requires content or source")
    source_path = Path(str(step["source"]))
    if not source_path.is_absolute():
        source_path = config_dir / source_path
    try:
        return source_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ConfigError(
            f"config-file install source not found: {source_path}"
        ) from error


def _parse_preflight_recipe(raw: dict[str, Any]) -> PreflightRecipe:
    return PreflightRecipe(
        required=bool(raw.get("required", True)),
        checks=tuple(_parse_preflight_check(check) for check in raw.get("checks", ())),
    )


def _parse_preflight_check(raw: dict[str, Any]) -> PreflightCheck:
    return PreflightCheck(
        name=str(raw["name"]),
        kind=str(raw["kind"]),
        required=bool(raw.get("required", True)),
        command=tuple(str(item) for item in raw.get("command", ())),
        env=tuple(str(item) for item in raw.get("env", ())),
        prompt=str(raw["prompt"]) if "prompt" in raw else None,
        expect_tool_calls=tuple(str(item) for item in raw.get("expect_tool_calls", ())),
    )
