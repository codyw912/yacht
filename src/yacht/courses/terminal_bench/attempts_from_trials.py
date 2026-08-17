from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from yacht import __version__
from yacht.config.loader import load_regatta
from yacht.contracts.schemas import (
    TASK_ATTEMPT_SCHEMA,
    SchemaValidationError,
    validate_harness_evidence_document,
    validate_task_attempt_document,
)
from yacht.harnesses.claude_code import (
    SESSION_TRANSCRIPT_EVIDENCE,
    mcp_server_namespace,
    skill_stages_from_session_transcript,
    tool_calls_from_session_transcript,
)
from yacht.harnesses.codex import CODEX_JSONL_EVIDENCE, parse_codex_jsonl
from yacht.harnesses.mcp_config import provider_mcp_namespace
from yacht.harnesses.omp import OMP_JSONL_EVIDENCE, parse_omp_jsonl
from yacht.harnesses.pi import PI_JSONL_EVIDENCE, tool_calls_from_pi_jsonl
from yacht.courses.terminal_bench.harness import HARBOR_JOB_NAME
from yacht.domain.model import (
    Comparison,
    ConfigError,
    Regatta,
    RiggingRecipe,
    RuntimeRecipe,
    SecretReference,
    Task,
    Vessel,
)
from yacht.logbook.paths import task_attempt_path
from yacht.runtimes.tool_capabilities import provided_mcp_install_provider
from yacht.workflows.benchmark_launcher_handoff import (
    native_report_path_from_launcher_handoff,
)
from yacht.workflows.provenance import tool_provenance


MACHINE_EVIDENCE_FORMAT = "terminal-bench-harbor-trial"
NATIVE_ROLLOUT_PROMPT = (
    "Task instruction delivered natively by the Harbor harness inside the "
    "task environment."
)


def write_terminal_bench_attempts_from_trials(
    *,
    config_path: Path,
    logbook_dir: Path,
    vessel_name: str,
    comparison_name: str | None = None,
) -> dict[str, Any]:
    regatta = load_regatta(config_path)
    vessel = _vessel(regatta, vessel_name)
    comparison = _comparison(regatta, vessel_name, comparison_name)
    runtime = _runtime(regatta, vessel)

    native_report_path = native_report_path_from_launcher_handoff(
        logbook_dir=logbook_dir,
        vessel_name=vessel_name,
    )
    report = _load_native_report(native_report_path)
    trials_by_task = _trials_by_task(report)

    artifact_paths = []
    completed = 0
    for task in regatta.course.tasks:
        trial = trials_by_task.get(task.id)
        artifact = _attempt_from_trial(
            regatta=regatta,
            comparison=comparison,
            vessel=vessel,
            runtime=runtime,
            task=task,
            trial=trial,
            native_report_path=native_report_path,
        )
        validate_task_attempt_document(artifact)
        artifact_path = task_attempt_path(logbook_dir, comparison, vessel, task)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(artifact, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifact_paths.append(str(artifact_path))
        if artifact["status"] == "completed":
            completed += 1

    return {
        "status": "completed",
        "mode": "native-rollout",
        "vessel": vessel_name,
        "comparison": comparison.name,
        "attempt_count": len(artifact_paths),
        "completed_attempts": completed,
        "failed_attempts": len(artifact_paths) - completed,
        "artifact_paths": artifact_paths,
    }


def _attempt_from_trial(
    *,
    regatta: Regatta,
    comparison: Comparison,
    vessel: Vessel,
    runtime: RuntimeRecipe,
    task: Task,
    trial: dict[str, Any] | None,
    native_report_path: Path,
) -> dict[str, Any]:
    completed = (
        trial is not None
        and trial.get("exception") is None
        and trial.get("reward") is not None
    )
    trial_dir = _trial_dir(trial, native_report_path)
    artifact = {
        "schema": TASK_ATTEMPT_SCHEMA,
        "regatta": regatta.name,
        "course": regatta.course.name,
        "comparison": comparison.name,
        "vessel": vessel.name,
        "model": vessel.model,
        "rigging": list(vessel.rigging),
        "runtime": runtime.name,
        "status": "completed" if completed else "failed",
        "task": _task_to_json(task),
        "provenance": _provenance(regatta, vessel, runtime, trial),
        "runtime_context": {
            "backend": runtime.backend,
            "harness": runtime.harness,
            "agent": runtime.harness,
            "temp_home": trial_dir,
            "workspace_path": trial_dir,
            "command_prefix": [],
            "command": ["harbor", "run"],
            "cleanup_paths": [],
        },
        "prompt": NATIVE_ROLLOUT_PROMPT,
        "agent": _agent_to_json(trial, trial_dir, completed),
        "metrics": _metrics(trial),
        "secret_refs": _secret_refs(regatta, vessel, runtime),
    }
    tool_expectations = _tool_expectations(regatta, vessel, runtime)
    if tool_expectations:
        artifact["tool_expectations"] = tool_expectations
    episodes = trial.get("episodes") if isinstance(trial, dict) else None
    if isinstance(episodes, dict):
        artifact["episodes"] = episodes
    return artifact


def _provenance(
    regatta: Regatta,
    vessel: Vessel,
    runtime: RuntimeRecipe,
    trial: dict[str, Any] | None,
) -> dict[str, Any]:
    agent = trial.get("agent") if isinstance(trial, dict) else None
    agent = agent if isinstance(agent, dict) else {}
    return {
        "yacht": {"version": __version__},
        "harness": {
            "name": runtime.harness,
            "version": _non_empty(agent.get("version")),
        },
        "model": {
            "configured": vessel.model,
            "resolved": _non_empty(agent.get("model")),
        },
        "runtime": {
            "backend": runtime.backend,
            "image": runtime.image,
        },
        "tools": tool_provenance(regatta, vessel),
    }


def _agent_to_json(
    trial: dict[str, Any] | None,
    trial_dir: str,
    completed: bool,
) -> dict[str, Any]:
    tool_calls, evidence_source = _observed_tool_calls(Path(trial_dir))
    payload = {
        "exit_code": 0 if completed else 1,
        "response": "",
        "tool_calls": tool_calls,
        "transcript_path": trial_dir,
        "machine_evidence": _machine_evidence(trial),
    }
    if evidence_source is not None:
        payload["tool_call_evidence"] = evidence_source
    if evidence_source == SESSION_TRANSCRIPT_EVIDENCE:
        skill_stages = _session_skill_stages(Path(trial_dir) / "agent" / "sessions")
        if skill_stages:
            payload["skill_stages"] = skill_stages
    elif evidence_source in {OMP_JSONL_EVIDENCE, CODEX_JSONL_EVIDENCE}:
        skill_stages = _native_stream_skill_stages(Path(trial_dir), evidence_source)
        if skill_stages:
            payload["skill_stages"] = skill_stages
    return payload


_SKILL_INSTALL_TARGET = re.compile(r"^\.claude/skills/([^/]+)/SKILL\.md$")
_FRONTMATTER_NAME = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)

# A per-server tool-name convention is guaranteed either natively —
# Claude Code names MCP tools mcp__<server>__<tool> — or by a rigged
# provider whose rendered configuration pins its own convention for a
# harness that doesn't natively namespace (ADR 0024); the provider's
# marker comes from its namespace_format, which need not match Claude
# Code's. A harness with neither guarantee gets no MCP expectation
# rather than a marker its transcripts can never match.
_MCP_NAMESPACED_HARNESSES = {"claude-code"}


def _tool_expectations(
    regatta: Regatta,
    vessel: Vessel,
    runtime: RuntimeRecipe,
) -> list[dict[str, Any]]:
    """Expected invocation markers for the vessel's installed tools,
    derived rather than configured where possible: a skill's marker
    comes from the SKILL.md it installs, an extension's from its
    declared expected_tool_calls, an MCP server's from the tool
    namespace its install step's target names (ADR 0022). Tools that
    declare nothing yield no expectation — an unmeasurable claim is
    omitted, not invented."""
    expectations: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_servers: set[str] = set()
    riggings = tuple(
        rigging
        for name in vessel.rigging
        if (rigging := regatta.rigging_recipes.get(name)) is not None
    )
    provider = provided_mcp_install_provider(
        runtime.harness, riggings, regatta.tool_capabilities
    )
    mcp_namespaced = runtime.harness in _MCP_NAMESPACED_HARNESSES or (
        provider is not None and provider.pins_namespace
    )
    for rigging_name in vessel.rigging:
        rigging = regatta.rigging_recipes.get(rigging_name)
        if rigging is None:
            continue
        installed_skills = _installed_skill_names(rigging)
        for tool_name in rigging.tools:
            if tool_name in seen:
                continue
            capability = regatta.tool_capabilities.get(tool_name)
            if capability is None:
                continue
            expected_calls: list[str] = []
            if capability.kind == "agent-skill":
                skill = _skill_for_tool(tool_name, installed_skills)
                expected_calls = [f"Skill:{skill}"]
            elif (
                capability.kind == "agent-extension" and capability.expected_tool_calls
            ):
                expected_calls = list(capability.expected_tool_calls)
            if not expected_calls:
                continue
            seen.add(tool_name)
            expectations.append(
                {
                    "tool": tool_name,
                    "kind": capability.kind,
                    "expected_calls": expected_calls,
                }
            )
        if not mcp_namespaced:
            continue
        for step in rigging.install:
            if step.method != "mcp-server":
                continue
            server = str(step.target)
            if server in seen_servers:
                continue
            seen_servers.add(server)
            if runtime.harness in _MCP_NAMESPACED_HARNESSES:
                marker = mcp_server_namespace(server)
            else:
                marker = provider_mcp_namespace(provider, server)
            expectations.append(
                {
                    "tool": server,
                    "kind": "mcp-server",
                    "expected_calls": [marker],
                }
            )
    return expectations


def _installed_skill_names(rigging: RiggingRecipe) -> list[str]:
    names = []
    for step in rigging.install:
        if step.method == "skill":
            names.append(_skill_name_from_content(step.content) or step.target)
            continue
        if step.method != "config-file":
            continue
        match = _SKILL_INSTALL_TARGET.match(step.target)
        if match is None:
            continue
        names.append(_skill_name_from_content(step.content) or match.group(1))
    return list(dict.fromkeys(names))


def _skill_name_from_content(content: str | None) -> str | None:
    """The skill name Claude Code invokes by is the SKILL.md frontmatter
    name, not the tool's config name — read it from the installed
    content when present."""
    if content is None or not content.lstrip().startswith("---"):
        return None
    body = content.lstrip().removeprefix("---")
    frontmatter = body.split("---", 1)[0]
    match = _FRONTMATTER_NAME.search(frontmatter)
    if match is None:
        return None
    return match.group(1)


def _skill_for_tool(tool_name: str, installed_skills: list[str]) -> str:
    if tool_name in installed_skills:
        return tool_name
    if len(installed_skills) == 1:
        return installed_skills[0]
    return tool_name


def _session_skill_stages(sessions_dir: Path) -> list[dict[str, str]]:
    if not sessions_dir.is_dir():
        return []
    stages: list[dict[str, str]] = []
    seen: set[str] = set()
    for transcript_path in sorted(sessions_dir.rglob("*.jsonl")):
        try:
            text = transcript_path.read_text(encoding="utf-8")
        except OSError:
            continue
        parsed = skill_stages_from_session_transcript(text)
        if parsed is None:
            continue
        for stage in parsed:
            name = stage["skill"]
            if name in seen:
                continue
            seen.add(name)
            stages.append(stage)
    return stages


def _observed_tool_calls(trial_dir: Path) -> tuple[list[str], str | None]:
    """Observed tool calls from the trial's preserved evidence, with the
    source that measured them. (calls=[], source=None) means unmeasured —
    no preserved trajectory said anything, which is different from a
    trajectory that shows no tool was called."""
    evidence_calls = _harness_evidence_tool_calls(
        trial_dir / "agent" / "harness-evidence.json"
    )
    if evidence_calls is not None:
        return evidence_calls, "harness-evidence"
    session_calls = _session_tool_calls(trial_dir / "agent" / "sessions")
    if session_calls is not None:
        return session_calls, SESSION_TRANSCRIPT_EVIDENCE
    omp_calls = _native_stream_tool_calls(
        _native_stream_paths(trial_dir, "omp.jsonl"), parse_omp_jsonl
    )
    if omp_calls is not None:
        return list(omp_calls), OMP_JSONL_EVIDENCE
    codex_calls = _native_stream_tool_calls(
        _native_stream_paths(trial_dir, "codex.jsonl"), parse_codex_jsonl
    )
    if codex_calls is not None:
        return list(codex_calls), CODEX_JSONL_EVIDENCE
    pi_calls = _pi_output_tool_calls(trial_dir / "agent" / "pi.txt")
    if pi_calls is not None:
        return list(pi_calls), PI_JSONL_EVIDENCE
    return [], None


def _harness_evidence_tool_calls(evidence_path: Path) -> list[str] | None:
    if not evidence_path.is_file():
        return None
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        validate_harness_evidence_document(payload)
    except (OSError, json.JSONDecodeError, SchemaValidationError):
        return None
    if "tool_calls" not in payload:
        return None
    names = [
        str(entry["name"])
        for entry in payload["tool_calls"]
        if isinstance(entry, dict) and entry.get("name")
    ]
    return list(dict.fromkeys(names))


def _session_tool_calls(sessions_dir: Path) -> list[str] | None:
    if not sessions_dir.is_dir():
        return None
    observed: list[str] = []
    measured = False
    for transcript_path in sorted(sessions_dir.rglob("*.jsonl")):
        try:
            text = transcript_path.read_text(encoding="utf-8")
        except OSError:
            continue
        tool_calls = tool_calls_from_session_transcript(text)
        if tool_calls is None:
            continue
        measured = True
        observed.extend(tool_calls)
    if not measured:
        return None
    return list(dict.fromkeys(observed))


def _pi_output_tool_calls(output_path: Path) -> tuple[str, ...] | None:
    if not output_path.is_file():
        return None
    try:
        text = output_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return tool_calls_from_pi_jsonl(text)


def _native_stream_paths(trial_dir: Path, name: str) -> list[Path]:
    root = trial_dir / "agent" / name
    if root.is_file():
        return [root]
    episodes_dir = trial_dir / "agent" / "episodes"
    if not episodes_dir.is_dir():
        return []
    return sorted(episodes_dir.glob(f"*/{name}"))


def _native_stream_tool_calls(paths: list[Path], parser) -> tuple[str, ...] | None:
    observed: list[str] = []
    measured = False
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parsed = parser(text)
        if parsed is None:
            continue
        measured = True
        tool_calls = parsed.get("tool_calls")
        if isinstance(tool_calls, tuple):
            observed.extend(tool_calls)
    if not measured:
        return None
    return tuple(dict.fromkeys(observed))


def _native_stream_skill_stages(
    trial_dir: Path, evidence_source: str
) -> list[dict[str, str]]:
    if evidence_source == OMP_JSONL_EVIDENCE:
        paths = _native_stream_paths(trial_dir, "omp.jsonl")
        parser = parse_omp_jsonl
    elif evidence_source == CODEX_JSONL_EVIDENCE:
        paths = _native_stream_paths(trial_dir, "codex.jsonl")
        parser = parse_codex_jsonl
    else:
        return []
    stages: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in paths:
        try:
            parsed = parser(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if parsed is None:
            continue
        for stage in parsed.get("skill_stages") or ():
            if not isinstance(stage, dict):
                continue
            name = stage.get("skill")
            if not isinstance(name, str) or name in seen:
                continue
            seen.add(name)
            stages.append(dict(stage))
    return stages


def _machine_evidence(trial: dict[str, Any] | None) -> dict[str, Any]:
    evidence: dict[str, Any] = {"format": MACHINE_EVIDENCE_FORMAT}
    if trial is None:
        evidence["status"] = "trial-missing"
        return evidence
    for key in ("trial_name", "trial_dir", "started_at", "finished_at"):
        value = trial.get(key)
        if isinstance(value, str) and value:
            evidence[key] = value
    reward = trial.get("reward")
    if isinstance(reward, (int, float)) and not isinstance(reward, bool):
        evidence["reward"] = float(reward)
    agent = trial.get("agent")
    if isinstance(agent, dict):
        model = _non_empty(agent.get("model"))
        if model is not None:
            evidence["model"] = model
        harness_version = _non_empty(agent.get("version"))
        if harness_version is not None:
            evidence["harness_version"] = harness_version
    usage = trial.get("usage")
    if isinstance(usage, dict):
        numeric_usage = {
            key: value
            for key, value in usage.items()
            if key != "cost_usd"
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value >= 0
        }
        if numeric_usage:
            evidence["usage"] = numeric_usage
        cost = usage.get("cost_usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
            evidence["cost"] = {"total": cost}
    episodes = trial.get("episodes")
    if isinstance(episodes, dict) and isinstance(episodes.get("items"), list):
        evidence["episodes"] = episodes["items"]
    exception = trial.get("exception")
    if isinstance(exception, dict):
        evidence["exception"] = {
            "type": str(exception.get("type")),
            "message": str(exception.get("message")),
        }
    return evidence


def _metrics(trial: dict[str, Any] | None) -> dict[str, Any]:
    tokens = 0
    duration = 0.0
    if trial is not None:
        usage = trial.get("usage")
        if isinstance(usage, dict):
            for key in ("input_tokens", "output_tokens"):
                value = usage.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    tokens += max(value, 0)
        duration = _duration_seconds(trial)
    return {"tokens": tokens, "duration_seconds": duration}


def _duration_seconds(trial: dict[str, Any]) -> float:
    started = _parse_timestamp(trial.get("started_at"))
    finished = _parse_timestamp(trial.get("finished_at"))
    if started is None or finished is None:
        return 0.0
    seconds = (finished - started).total_seconds()
    return seconds if seconds >= 0 else 0.0


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _trials_by_task(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    trials = report.get("trials")
    if not isinstance(trials, list):
        raise ConfigError(
            "terminal-bench native report does not include trial summaries"
        )
    by_task: dict[str, dict[str, Any]] = {}
    for trial in trials:
        if not isinstance(trial, dict):
            raise ConfigError("terminal-bench trial summary must be a JSON object")
        task_name = trial.get("task_name")
        if not isinstance(task_name, str) or not task_name:
            raise ConfigError("terminal-bench trial summary is missing task_name")
        by_task[task_name] = trial
    return by_task


def _trial_dir(trial: dict[str, Any] | None, native_report_path: Path) -> str:
    if trial is not None:
        trial_dir = trial.get("trial_dir")
        if isinstance(trial_dir, str) and trial_dir:
            return trial_dir
    return str(native_report_path.parent.parent / "harbor-trials" / HARBOR_JOB_NAME)


def _load_native_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"native report not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"native report is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigError("native report must be a JSON object")
    return payload


def _vessel(regatta: Regatta, vessel_name: str) -> Vessel:
    for vessel in regatta.vessels:
        if vessel.name == vessel_name:
            return vessel
    raise ConfigError(f"vessel {vessel_name} is not defined in the regatta config")


def _comparison(
    regatta: Regatta,
    vessel_name: str,
    comparison_name: str | None,
) -> Comparison:
    matches = [
        comparison
        for comparison in regatta.comparisons
        if vessel_name in comparison.vessels
        and (comparison_name is None or comparison.name == comparison_name)
    ]
    if not matches:
        raise ConfigError(f"vessel {vessel_name} is not part of a matching comparison")
    if len(matches) > 1:
        raise ConfigError(
            f"vessel {vessel_name} is in multiple comparisons; pass --comparison"
        )
    return matches[0]


def _runtime(regatta: Regatta, vessel: Vessel) -> RuntimeRecipe:
    if vessel.runtime is None:
        raise ConfigError(
            f"vessel {vessel.name} must declare a runtime for terminal-bench"
        )
    runtime = regatta.runtime_recipes.get(vessel.runtime)
    if runtime is None:
        raise ConfigError(
            f"vessel {vessel.name} references undefined runtime {vessel.runtime}"
        )
    return runtime


def _task_to_json(task: Task) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": task.id,
        "title": task.title,
        "difficulty": task.difficulty,
    }
    if task.problem_statement is not None:
        payload["problem_statement"] = task.problem_statement
    return payload


def _secret_refs(
    regatta: Regatta,
    vessel: Vessel,
    runtime: RuntimeRecipe,
) -> list[dict[str, Any]]:
    names = list(runtime.required_secrets)
    for rigging_name in vessel.rigging:
        rigging = regatta.rigging_recipes.get(rigging_name)
        if rigging is not None:
            names.extend(rigging.required_secrets)
    return [_secret_ref(name, regatta.secrets[name]) for name in dict.fromkeys(names)]


def _secret_ref(name: str, secret: SecretReference) -> dict[str, Any]:
    if secret.source == "env" and secret.name is not None:
        ref = secret.name
    elif secret.source == "file" and secret.path is not None:
        ref = secret.path
    else:
        ref = secret.source
    return {"name": name, "source": secret.source, "ref": ref, "redacted": True}


def _non_empty(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
