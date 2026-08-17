"""Pure helpers for episodic trials (ADR 0025).

An episode plan is rendered and validated host-side by
`yacht.courses.episodes.render_episode_plan` and embedded into the
terminal-bench job document. This module re-validates the plan's shape
defensively on the launcher side (it arrives as ordinary agent kwargs,
one more hop removed from the validator that produced it), and
supplies the other pure, harbor-free pieces the episodic run loop in
`agents.py` needs: task identity, claude stream-result parsing, ending
classification, session/verifier bookkeeping, and evidence merging.

No harbor imports here: this module is unit-tested from the yacht repo
without the harbor package installed, mirroring rigging.py and
declared_support.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ENDED_NATURAL = "natural"
ENDED_CAP = "cap"
ENDED_TIMEOUT = "timeout"
ENDED_ERROR = "error"

EVIDENCE_SCHEMA = "yacht.harness-evidence.v1"

_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


class EpisodePlanError(RuntimeError):
    pass


def plan_for_task(
    episodes_kwarg: dict[str, Any] | None, task_name: str
) -> dict[str, Any] | None:
    """The validated episode plan for `task_name`, or None if not episodic.

    `episodes_kwarg` is the agent's `episodes` kwarg: a mapping of task
    name to plan, forwarded verbatim from the job document's
    `agent.episodes`. Absence of the kwarg, or of this task's entry in
    it, means the task runs single-shot as before. A present but
    malformed entry is always an `EpisodePlanError` — never a silent
    fall-through to single-shot — because the plan was supposed to have
    already been validated host-side; anything wrong here is a defect,
    not a legitimate "no episodes" signal.
    """
    if not episodes_kwarg:
        return None
    if task_name not in episodes_kwarg:
        return None
    plan = episodes_kwarg[task_name]
    if not isinstance(plan, dict):
        raise EpisodePlanError(f"episode plan for {task_name} must be an object")

    maximum = plan.get("max")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 2:
        raise EpisodePlanError(
            f"episode plan for {task_name}: max must be an integer >= 2"
        )

    verify_between = plan.get("verify_between")
    if not isinstance(verify_between, bool):
        raise EpisodePlanError(
            f"episode plan for {task_name}: verify_between must be a boolean"
        )

    instructions = plan.get("instructions")
    if not isinstance(instructions, list) or len(instructions) != maximum - 1:
        raise EpisodePlanError(
            f"episode plan for {task_name}: instructions must contain max - 1 entries"
        )
    for entry in instructions:
        if not isinstance(entry, str) or not entry.strip():
            raise EpisodePlanError(
                f"episode plan for {task_name}: instructions entries must be "
                "non-empty strings"
            )

    result: dict[str, Any] = {
        "max": maximum,
        "verify_between": verify_between,
        "instructions": list(instructions),
    }
    for key in ("max_turns", "timeout_seconds"):
        if key in plan:
            value = plan[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise EpisodePlanError(
                    f"episode plan for {task_name}: {key} must be an integer >= 1"
                )
            result[key] = value
    return result


def task_identity(trial_dir: Path) -> tuple[str, Path]:
    """The task's name and directory from the trial's Harbor config.json.

    Harbor writes `trial_dir/config.json` before the agent runs; its
    `task.path` names the local task directory the container is built
    from. Registry tasks (named, not path-addressed) have no local
    directory to read the episode plan or deltas from, so they raise
    the same way a missing/malformed config does.
    """
    config_path = trial_dir / "config.json"
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as error:
        raise EpisodePlanError(f"{config_path} could not be read: {error}") from error
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise EpisodePlanError(f"{config_path} is not valid JSON: {error}") from error
    task = payload.get("task") if isinstance(payload, dict) else None
    if not isinstance(task, dict):
        raise EpisodePlanError(f"{config_path} is missing a task object")
    path = task.get("path")
    if not isinstance(path, str) or not path:
        raise EpisodePlanError(
            f"{config_path} task has no local path; registry tasks are not "
            "supported for episodic trials"
        )
    task_dir = Path(path)
    return task_dir.name, task_dir


def parse_claude_stream_result(text: str) -> dict[str, Any]:
    """The last `{"type": "result"}` line of a claude-code stream-json run.

    Non-JSON lines (progress/log noise) are skipped. Absence of any
    result line (a crash before completion) is reported as all-None,
    not an error: the caller decides what that means for the episode.
    """
    result_line: dict[str, Any] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("type") == "result":
            result_line = payload

    if result_line is None:
        return {"subtype": None, "usage": None, "cost_usd": None}

    subtype = result_line.get("subtype")
    subtype = subtype if isinstance(subtype, str) else None

    usage: dict[str, int] | None = None
    usage_raw = result_line.get("usage")
    if isinstance(usage_raw, dict):
        filtered = {
            key: usage_raw[key]
            for key in _USAGE_KEYS
            if isinstance(usage_raw.get(key), int)
            and not isinstance(usage_raw.get(key), bool)
            and usage_raw[key] >= 0
        }
        usage = filtered or None

    cost_raw = result_line.get("total_cost_usd")
    cost_usd = (
        float(cost_raw)
        if isinstance(cost_raw, (int, float)) and not isinstance(cost_raw, bool)
        else None
    )

    return {"subtype": subtype, "usage": usage, "cost_usd": cost_usd}


def claude_episode_ended(subtype: str | None, timed_out: bool, errored: bool) -> str:
    """Classify how a claude-code episode ended (ADR 0025 ending taxonomy).

    Timeout (the driver's wall-clock backstop) always wins, since it
    can fire regardless of what the harness itself reported. Otherwise
    a `max_turns` cap is a normal, expected ending. `success` with no
    other error is a natural completion; anything else is an error.
    """
    if timed_out:
        return ENDED_TIMEOUT
    if subtype == "error_max_turns":
        return ENDED_CAP
    if subtype == "success" and not errored:
        return ENDED_NATURAL
    return ENDED_ERROR


def parse_omp_stream_result(text: str) -> dict[str, Any]:
    """Usage, cost, and completion from a captured OMP `--mode json` stream."""
    ended = None
    usage = None
    cost_usd = None
    for event in _jsonl_objects(text):
        if event.get("type") == "agent_end":
            ended = ENDED_NATURAL
        if event.get("type") != "message_end":
            continue
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        parsed_usage, parsed_cost = _omp_usage(message.get("usage"))
        if parsed_usage is not None:
            usage = parsed_usage
        if parsed_cost is not None:
            cost_usd = parsed_cost
    return {"ended": ended, "usage": usage, "cost_usd": cost_usd}


def parse_codex_stream_result(text: str) -> dict[str, Any]:
    """Usage and completion from a captured Codex `exec --json` stream."""
    ended = None
    usage = None
    for event in _jsonl_objects(text):
        event_type = event.get("type")
        if event_type in {"turn.failed", "error"}:
            ended = ENDED_ERROR
        elif event_type == "turn.completed":
            ended = ENDED_NATURAL
            parsed = _codex_usage(event.get("usage"))
            if parsed is not None:
                usage = parsed
    return {"ended": ended, "usage": usage, "cost_usd": None}


def jsonl_episode_ended(
    stream_ended: str | None, timed_out: bool, errored: bool
) -> str:
    """Classify an OMP or Codex episode. Neither CLI has a native turn cap."""
    if timed_out:
        return ENDED_TIMEOUT
    if errored or stream_ended == ENDED_ERROR:
        return ENDED_ERROR
    if stream_ended == ENDED_NATURAL:
        return ENDED_NATURAL
    return ENDED_ERROR


def snapshot_stream(logs_dir: Path, episode_dir: Path, name: str) -> str:
    """Copy a native JSONL stream into the episode dir and clear the source."""
    source = logs_dir / name
    text = ""
    if source.is_file():
        text = source.read_text(encoding="utf-8", errors="replace")
        episode_dir.mkdir(parents=True, exist_ok=True)
        (episode_dir / name).write_text(text, encoding="utf-8")
        source.unlink()
    return text


def _jsonl_objects(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _omp_usage(usage: Any) -> tuple[dict[str, int] | None, float | None]:
    if not isinstance(usage, dict):
        return None, None
    parsed: dict[str, int] = {}
    for source, dest in (
        ("input", "input_tokens"),
        ("output", "output_tokens"),
        ("cacheRead", "cache_read_tokens"),
        ("cacheWrite", "cache_write_tokens"),
    ):
        value = usage.get(source)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            parsed[dest] = value
    cost_usd = None
    cost = usage.get("cost")
    if isinstance(cost, dict):
        total = cost.get("total")
        if isinstance(total, (int, float)) and not isinstance(total, bool):
            cost_usd = float(total)
    return (parsed or None), cost_usd


def _codex_usage(usage: Any) -> dict[str, int] | None:
    if not isinstance(usage, dict):
        return None
    parsed: dict[str, int] = {}
    for source, dest in (
        ("input_tokens", "input_tokens"),
        ("output_tokens", "output_tokens"),
        ("cached_input_tokens", "cache_read_tokens"),
        ("cache_write_input_tokens", "cache_write_tokens"),
    ):
        value = usage.get(source)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            parsed[dest] = value
    return parsed or None


def sessions_manifest(sessions_root: Path) -> list[dict[str, Any]]:
    """`{"path", "size"}` for every `*.jsonl` session file under root."""
    if not sessions_root.is_dir():
        return []
    entries = [
        {
            "path": item.relative_to(sessions_root).as_posix(),
            "size": item.stat().st_size,
        }
        for item in sessions_root.rglob("*.jsonl")
        if item.is_file()
    ]
    entries.sort(key=lambda entry: entry["path"])
    return entries


def read_reward(verifier_dir: Path) -> float | None:
    """The reward from an inter-episode verifier run, or None.

    Mirrors terminal_bench/harness.py's `_trial_reward` single-key
    fallback: `reward.json`'s `"reward"` key first, else its sole key
    if it has exactly one; `reward.txt`'s bare float otherwise. Any
    unparseable/missing state falls through to the next source, ending
    in None rather than raising — a missing mid-trial reward is a data
    point, not a trial error.
    """
    value = _read_reward_json(verifier_dir / "reward.json")
    if value is not None:
        return value
    return _read_reward_txt(verifier_dir / "reward.txt")


def _read_reward_json(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not payload:
        return None
    if "reward" in payload:
        value = payload["reward"]
    elif len(payload) == 1:
        value = next(iter(payload.values()))
    else:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _read_reward_txt(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        return float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _has_valid_cache_read_tokens(episode: dict[str, Any]) -> bool:
    """Whether `episode`'s usage carries a non-negative int cache_read_tokens.

    A native (non-evidence_map) declared harness is not validated
    launcher-side before merge, so a non-int or negative value here
    counts as "not having it" — the existing sum-only-if-every-episode-
    has-it rule then correctly omits the field instead of crashing.
    """
    usage = episode.get("usage")
    if not isinstance(usage, dict) or "cache_read_tokens" not in usage:
        return False
    value = usage["cache_read_tokens"]
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def merged_declared_evidence(per_episode: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold per-episode yacht.harness-evidence.v1 docs into one.

    `response` comes from the last episode (the final state of the
    relay); usage is summed across every episode; `cache_read_tokens`
    is summed only when every episode reported it (a partial sum would
    understate cache usage, not report it faithfully); tool calls are
    merged by name; `model` is the last episode that named one; `cost`
    is summed only when every episode has one, for the same reason as
    cache tokens.

    Raises `EpisodePlanError` on an empty list: a relay always runs at
    least one episode, so an empty list here means the caller lost
    evidence upstream (e.g. a crash before episode 1 finished) rather
    than legitimately having nothing to merge.
    """
    if not per_episode:
        raise EpisodePlanError("merged_declared_evidence requires at least one episode")

    response = str(per_episode[-1].get("response", ""))

    total_input = sum(int(episode["usage"]["input_tokens"]) for episode in per_episode)
    total_output = sum(
        int(episode["usage"]["output_tokens"]) for episode in per_episode
    )
    usage: dict[str, Any] = {
        "input_tokens": total_input,
        "output_tokens": total_output,
    }
    if all(_has_valid_cache_read_tokens(episode) for episode in per_episode):
        usage["cache_read_tokens"] = sum(
            int(episode["usage"]["cache_read_tokens"]) for episode in per_episode
        )

    document: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        "response": response,
        "usage": usage,
    }

    tool_calls: dict[str, int] = {}
    for episode in per_episode:
        for call in episode.get("tool_calls") or []:
            name = call.get("name")
            count = call.get("count")
            if (
                isinstance(name, str)
                and isinstance(count, int)
                and not isinstance(count, bool)
            ):
                tool_calls[name] = tool_calls.get(name, 0) + count
    if tool_calls:
        document["tool_calls"] = [
            {"name": name, "count": count} for name, count in tool_calls.items()
        ]

    model: str | None = None
    for episode in per_episode:
        candidate = episode.get("model")
        if isinstance(candidate, str) and candidate:
            model = candidate
    if model is not None:
        document["model"] = model

    if all(
        isinstance(episode.get("cost"), dict)
        and isinstance(episode["cost"].get("total_usd"), (int, float))
        and not isinstance(episode["cost"].get("total_usd"), bool)
        for episode in per_episode
    ):
        document["cost"] = {
            "total_usd": sum(
                float(episode["cost"]["total_usd"]) for episode in per_episode
            )
        }

    return document


def episode_record(
    *,
    index: int,
    ended: str,
    started_at: str,
    finished_at: str,
    usage: dict[str, Any] | None = None,
    cost_usd: float | None = None,
    reward: float | None = None,
) -> dict[str, Any]:
    """One episode's entry for the relay summary, omitting unset fields."""
    record: dict[str, Any] = {
        "index": index,
        "ended": ended,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    if usage is not None:
        record["usage"] = usage
    if cost_usd is not None:
        record["cost_usd"] = cost_usd
    if reward is not None:
        record["reward"] = reward
    return record


def write_relay_summary(
    episodes_dir: Path,
    records: list[dict[str, Any]],
    to_resolution: int | None,
) -> None:
    """Write `episodes_dir/summary.json` describing the whole relay."""
    payload: dict[str, Any] = {"count": len(records), "items": records}
    if to_resolution is not None:
        payload["to_resolution"] = to_resolution
    episodes_dir.mkdir(parents=True, exist_ok=True)
    (episodes_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
