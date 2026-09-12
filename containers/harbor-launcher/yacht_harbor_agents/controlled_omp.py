"""Trusted controller for bounded single/retained/cold-capped OMP."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import shlex
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from yacht_harbor_agents.captures import (
    capture_via_exec,
    evidence_dir,
    write_host_capture,
)
from yacht_harbor_agents import episodes as episode_helpers

SCHEMA = "yacht.execution.v1"
_SENSITIVE_KEY = re.compile(
    r"(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|AUTH)", re.IGNORECASE
)
_EXCHANGE_LIMIT_SECONDS = 30
# Budget for the shutdown *ack* only.
_SHUTDOWN_LIMIT_SECONDS = 5
# Separate, longer budget for the driver process to actually exit after
# it acks. Reusing the ack budget for both meant the ack could consume
# nearly all of it and the transport close would be declared
# unconfirmed while the process was still exiting normally, which
# invalidated otherwise-good runs.
_CLOSE_LIMIT_SECONDS = 20
_QUIESCE_LIMIT_SECONDS = 15
# The driver enforces `message_timeout_seconds` itself, then needs a
# little room to abort outstanding tools and report the settle. Waiting
# exactly the SDK deadline would time the controller out first and throw
# away that evidence. The grace admits no new model work.
_SETTLE_GRACE_SECONDS = 20
# node, not python3: the pinned prebuilt task image is FROM node and
# need not ship python3. The starttime recheck runs in-container so a
# recycled PID is never signalled in place of the selected process.
_NODE_KILL = r"""
const fs = require("fs");
const pid = Number(process.env.YACHT_REAP_PID);
const want = Number(process.env.YACHT_REAP_STARTTIME);
try {
  const stat = fs.readFileSync("/proc/" + pid + "/stat", "utf8");
  const rest = stat.slice(stat.lastIndexOf(")") + 1).trim().split(/\s+/);
  if (Number(rest[19]) !== want) process.exit(0);
  if (rest[0] === "Z") process.exit(0);
} catch (err) {
  process.exit(0);
}
try {
  process.kill(-pid, "SIGKILL");
} catch (err) {
  try { process.kill(pid, "SIGKILL"); } catch (inner) {}
}
"""

_FRAME_USAGE_MAP = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cacheRead": "cache_read_tokens",
    "cacheWrite": "cache_write_tokens",
    "totalTokens": "total_tokens",
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "cache_read_tokens": "cache_read_tokens",
    "cache_write_tokens": "cache_write_tokens",
    "total_tokens": "total_tokens",
}


class ControlledOmpError(RuntimeError):
    pass


class DriverSession(Protocol):
    async def send(self, payload: dict[str, Any]) -> None: ...

    async def recv(self) -> dict[str, Any]: ...

    async def close(self) -> None: ...


FinalCleanupFn = Callable[..., Awaitable[None]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _secret_values(env: dict[str, str] | None) -> set[str]:
    values: set[str] = set()
    for key, value in (env or {}).items():
        if value and _SENSITIVE_KEY.search(key):
            values.add(value)
    return values


def _scrub(payload: Any, secrets: set[str], *, parent: str = "") -> Any:
    if isinstance(payload, dict):
        return {
            key: "[redacted]"
            if parent in {"env", "headers"}
            and isinstance(value, str)
            and value
            and _SENSITIVE_KEY.search(key)
            else _scrub(value, secrets, parent=key)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_scrub(value, secrets) for value in payload]
    if isinstance(payload, str):
        for secret in secrets:
            payload = payload.replace(secret, "[redacted]")
    return payload


def _load_plan_validator() -> Any:
    import importlib

    last_error: Exception | None = None
    for name in (
        "yacht_harbor_agents.execution_contract",
        "yacht._execution_contract",
    ):
        try:
            module = importlib.import_module(name)
        except ImportError as error:
            last_error = error
            continue
        validator = getattr(module, "validate_execution_plan", None)
        if validator is not None:
            return validator
    raise ControlledOmpError("canonical execution contract is absent") from last_error


def _validate_plan(plan: dict[str, Any]) -> None:
    _load_plan_validator()(plan)


def resolve_execution_plan(
    execution_kwarg: dict[str, Any] | None, logs_dir: Path
) -> dict[str, Any] | None:
    if not execution_kwarg:
        return None
    if "mode" in execution_kwarg:
        return dict(execution_kwarg)
    task_name, _task_dir = episode_helpers.task_identity(logs_dir.parent)
    plan = execution_kwarg.get(task_name)
    return dict(plan) if isinstance(plan, dict) else None


def _messages_from_plan(plan: dict[str, Any], instruction: str) -> list[dict[str, str]]:
    initial_id = str(plan.get("initial_turn_id") or "initial")
    messages = [{"id": initial_id, "instruction": instruction}]
    for turn in plan.get("turns") or []:
        messages.append(
            {"id": str(turn["id"]), "instruction": str(turn["instruction"])}
        )
    return messages


def _captures_after(
    plan: dict[str, Any], turn_id: str
) -> list[tuple[int, dict[str, Any]]]:
    found: list[tuple[int, dict[str, Any]]] = []
    for index, capture in enumerate(plan.get("captures") or []):
        if capture.get("after") == turn_id:
            found.append((index, capture))
    return found


def _normalize_usage(usage: Any) -> dict[str, int] | None:
    """Map native driver usage keys onto Harbor's token contract.

    `apply_usage_to_context` requires ints, so integral counts must stay
    ints; a non-integral value is unknown rather than silently rounded.
    """
    if not isinstance(usage, dict):
        return None
    parsed: dict[str, int] = {}
    for source, dest in _FRAME_USAGE_MAP.items():
        value = usage.get(source)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            continue
        if isinstance(value, float) and not value.is_integer():
            continue
        parsed[dest] = int(value)
    return parsed or None


def _normalize_cost(cost: Any) -> float | None:
    """Positive reported cost, or None when spend is unknown.

    The SDK synthesizes `0` when no pricing is available (subscription
    configs carry none), so a zero is "no pricing", not "free". Treating
    it as billed spend would publish a fabricated total, so it stays
    unknown. `null` is unknown too.
    """
    if isinstance(cost, bool) or cost is None:
        return None
    if isinstance(cost, (int, float)) and cost > 0:
        return float(cost)
    return None


def _settle_is_fatal(frame: dict[str, Any]) -> bool:
    if frame.get("success") is False:
        return True
    data = frame.get("data")
    if not isinstance(data, dict):
        return True
    if data.get("invalid"):
        return True
    if data.get("ended") == "error":
        return True
    quiescence = data.get("quiescence") or {}
    if isinstance(quiescence, dict) and quiescence.get("ready") is False:
        return True
    return False


def _may_continue(data: dict[str, Any]) -> bool:
    ended = data.get("ended")
    if ended in {"cap", "timeout"}:
        return bool(data.get("continuation_possible"))
    return True


async def _exchange(
    driver: DriverSession,
    payload: dict[str, Any],
    *,
    events_path: Path,
    secrets: set[str],
    timeout_seconds: float,
) -> dict[str, Any]:
    await asyncio.wait_for(driver.send(payload), timeout=timeout_seconds)
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ControlledOmpError("driver exchange timed out")
        frame = await asyncio.wait_for(driver.recv(), timeout=remaining)
        if frame.get("type") == "response" and frame.get("id") == payload["id"]:
            return frame
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_scrub(frame, secrets)) + "\n")


async def _write_summary_after_close(
    *,
    plan: dict[str, Any],
    valid: bool,
    ended: str,
    messages: list[dict[str, Any]],
    captures: list[dict[str, Any]],
    evidence: Path,
    logs_dir: Path,
    driver: DriverSession,
    model: str,
    session_ids: list[str],
    settings: dict[str, Any],
    publish_handoff: bool,
    error: str | None,
    final_cleanup: Callable[[], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    closed = True
    try:
        await asyncio.wait_for(driver.close(), timeout=_CLOSE_LIMIT_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception:
        # The transport did not confirm shutdown, so in-container writers
        # are unproven and the trusted handoff must be withheld.
        closed = False
    # A total is only reported when every delivered message reported that
    # key; otherwise the sum would understate real usage while looking
    # complete. Unknown stays unknown.
    usage: dict[str, int] = {}
    usage_keys: set[str] | None = None
    cost_usd: float | None = None
    cost_known = bool(messages)
    for item in messages:
        item_usage = item.get("usage")
        keys: set[str] = set()
        if isinstance(item_usage, dict):
            for key, value in item_usage.items():
                if isinstance(value, int) and not isinstance(value, bool):
                    usage[key] = usage.get(key, 0) + value
                    keys.add(key)
        usage_keys = keys if usage_keys is None else (usage_keys & keys)
        item_cost = item.get("cost_usd")
        if isinstance(item_cost, (int, float)) and not isinstance(item_cost, bool):
            cost_usd = (0.0 if cost_usd is None else cost_usd) + float(item_cost)
        else:
            cost_known = False
    usage = {key: value for key, value in usage.items() if key in (usage_keys or set())}
    if not cost_known:
        cost_usd = None
    if not closed:
        # Unproven in-container writers are an infrastructure failure.
        valid = False
        ended = "error"
        error = error or "transport close unconfirmed"
    elif final_cleanup is not None:
        try:
            await asyncio.wait_for(
                final_cleanup(),
                timeout=_QUIESCE_LIMIT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            valid = False
            ended = "error"
            error = error or "quiescence failed"
            publish_handoff = False
    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "mode": plan.get("mode"),
        "max_turns": int(plan["max_turns"]),
        "message_timeout_seconds": int(plan["message_timeout_seconds"]),
        "timeout_seconds": int(plan["timeout_seconds"]),
        "session_ids": list(session_ids),
        "messages": messages,
        "captures": captures,
        "valid": valid,
        "model": model,
        "harness": "omp",
        "harness_version": "18.1.17",
        "settings": dict(settings),
        "usage": usage,
        "cost_usd": cost_usd,
        "ended": ended,
        "handoff": {"verifier": "verifier/yacht-execution"},
    }
    if error:
        summary["error"] = error
    elif not valid:
        summary["error"] = "invalid"
    (evidence / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if publish_handoff and closed:
        handoff = logs_dir.parent / "verifier" / "yacht-execution"
        if handoff.exists():
            shutil.rmtree(handoff)
        handoff.mkdir(parents=True, exist_ok=True)
        shutil.copy2(evidence / "summary.json", handoff / "summary.json")
        (handoff / "manifest.json").write_text(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "valid": valid,
                    "ended": ended,
                    "captures": captures,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        for record in captures:
            artifact = record.get("artifact")
            if not artifact:
                continue
            source = evidence / artifact
            if source.is_file():
                shutil.copy2(source, handoff / artifact)
    return summary


async def _snapshot(
    environment: Any,
) -> tuple[list[dict[str, Any]], set[tuple[int, int]]]:
    """Container process scan plus the scanner's own identity chain.

    The scanner is spawned after the baseline, so without excluding its
    own identities every scan would select it and the reap loop could
    never converge.
    """
    from yacht_harbor_agents.quiesce import _NODE_SNAPSHOT

    command = "node -e " + shlex.quote(_NODE_SNAPSHOT)
    result = await environment.exec(command=command)
    if getattr(result, "return_code", 1) != 0:
        detail = (
            getattr(result, "stderr", None) or getattr(result, "stdout", None) or ""
        )
        raise ControlledOmpError(f"process snapshot failed: {detail}")
    payload = json.loads(result.stdout or '{"entries": [], "own": []}')
    if isinstance(payload, list):
        return payload, set()
    entries = payload.get("entries") or []
    own = {
        (int(pair[0]), int(pair[1]))
        for pair in payload.get("own") or []
        if isinstance(pair, (list, tuple)) and len(pair) == 2
    }
    return entries, own


async def run_controlled_omp(
    *,
    environment: Any,
    logs_dir: Path,
    instruction: str,
    model: str,
    plan: dict[str, Any],
    env: dict[str, str] | None = None,
    driver: DriverSession | None = None,
    final_cleanup: FinalCleanupFn | None = None,
) -> dict[str, Any]:
    _validate_plan(plan)
    if driver is None:
        raise ControlledOmpError("duplex driver is required")
    secrets = _secret_values(env)
    baseline_holder: dict[str, Any] = {"baseline": None}
    scanner_identities: set[tuple[int, int]] = set()

    async def production_final_cleanup(**kwargs: Any) -> None:
        from yacht_harbor_agents.quiesce import reap_from_entries

        baseline = baseline_holder["baseline"]
        if baseline is None:
            raise ControlledOmpError("missing process baseline")
        protect = set(kwargs.get("protect_pids") or [])
        for _attempt in range(6):
            entries, own = await _snapshot(environment)
            scanner_identities.update(own)
            reap = [
                (pid, starttime)
                for pid, starttime in reap_from_entries(
                    entries, baseline=baseline, protect_pids=protect
                )
                if (pid, starttime) not in scanner_identities
                and (pid, starttime) not in own
            ]
            if not reap:
                return
            for pid, starttime in reap:
                # node, not python3: the pinned prebuilt task image ships
                # node (the driver requires it) and need not have python3.
                # starttime is re-checked in-container so a recycled PID
                # is never signalled in place of the process we selected.
                await environment.exec(
                    command="node -e " + shlex.quote(_NODE_KILL),
                    env={
                        "YACHT_REAP_PID": str(int(pid)),
                        "YACHT_REAP_STARTTIME": str(int(starttime)),
                    },
                )
        raise ControlledOmpError("quiescence failed")

    cleanup_fn = final_cleanup or production_final_cleanup

    evidence = evidence_dir(logs_dir)
    evidence.mkdir(parents=True, exist_ok=True)
    events_path = evidence / "events.jsonl"
    started = time.monotonic()
    timeout_seconds = int(plan["timeout_seconds"])
    deadline = started + timeout_seconds
    # The driver compares this against `Date.now()`, so it must be an
    # absolute epoch instant, not a duration: sending a duration put the
    # deadline in 1970 and timed out every real prompt immediately.
    deadline_ms = int((time.time() + timeout_seconds) * 1000)
    max_turns = int(plan["max_turns"])
    message_timeout = int(plan["message_timeout_seconds"])
    valid = True
    ended = "natural"
    error: str | None = None
    captures: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    session_ids: list[str] = []
    settings: dict[str, Any] = {}
    next_id = 1
    protect_pids: set[int] = set()

    def allocate_id() -> str:
        nonlocal next_id
        value = str(next_id)
        next_id += 1
        return value

    async def shutdown() -> None:
        command_id = allocate_id()
        frame = await _exchange(
            driver,
            {"id": command_id, "type": "shutdown"},
            events_path=events_path,
            secrets=secrets,
            timeout_seconds=_SHUTDOWN_LIMIT_SECONDS,
        )
        if frame.get("success") is False:
            # The driver reported it could not dispose of the session, so
            # writers are unproven: invalidate rather than publish.
            data = frame.get("data")
            detail = ""
            if isinstance(data, dict):
                detail = str(data.get("error") or data.get("code") or "")
            raise ControlledOmpError(
                f"driver shutdown failed: {detail}"
                if detail
                else "driver shutdown failed"
            )

    async def finalize() -> dict[str, Any]:
        nonlocal valid, ended, error
        disposed = True
        try:
            await asyncio.wait_for(shutdown(), timeout=_SHUTDOWN_LIMIT_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            valid = False
            ended = "error"
            error = error or "shutdown failed"
            disposed = False

        async def run_final_cleanup() -> None:
            await cleanup_fn(
                environment=environment,
                protect_pids=protect_pids,
            )

        return await _write_summary_after_close(
            plan=plan,
            valid=valid,
            ended=ended,
            messages=messages,
            captures=captures,
            evidence=evidence,
            logs_dir=logs_dir,
            driver=driver,
            model=model,
            session_ids=session_ids,
            settings=settings,
            publish_handoff=disposed,
            error=error,
            final_cleanup=run_final_cleanup,
        )

    try:
        init_id = allocate_id()
        init_frame = await _exchange(
            driver,
            {
                "id": init_id,
                "type": "init",
                "model": model,
                "deadline_ms": deadline_ms,
            },
            events_path=events_path,
            secrets=secrets,
            timeout_seconds=min(
                _EXCHANGE_LIMIT_SECONDS, max(1, deadline - time.monotonic())
            ),
        )
        if not init_frame.get("success") or not isinstance(
            init_frame.get("data"), dict
        ):
            valid = False
            ended = "error"
            error = "init failed"
            return await finalize()
        init_data = init_frame["data"]
        protect_pids = {int(pid) for pid in init_data.get("protected_pids") or []}
        if init_data.get("session_id"):
            session_ids.append(str(init_data["session_id"]))
        policy = init_data.get("policy") or {}
        if not isinstance(policy, dict):
            raise ControlledOmpError("init policy must be an object")
        # Record the policy as reported. A bool-only filter silently
        # dropped non-boolean enforcement evidence such as
        # `memory.backend: "off"` and the enabled-tools roster, which is
        # exactly the evidence that proves what was enforced. The host
        # validator accepts JSON types, and this is already JSON.
        settings.update(policy)
        if final_cleanup is None:
            from yacht_harbor_agents.quiesce import baseline_from_entries

            baseline_entries, baseline_own = await _snapshot(environment)
            scanner_identities.update(baseline_own)
            baseline_holder["baseline"] = baseline_from_entries(baseline_entries)
        script = _messages_from_plan(plan, instruction)
        for message in script:
            if time.monotonic() >= deadline:
                ended = "timeout"
                break
            remaining = min(
                float(message_timeout) + _SETTLE_GRACE_SECONDS,
                max(1.0, deadline - time.monotonic() + _SETTLE_GRACE_SECONDS),
            )
            started_at = _utc_now()
            frame = await _exchange(
                driver,
                {
                    "id": allocate_id(),
                    "type": "prompt",
                    "turn_id": message["id"],
                    "message": message["instruction"],
                    "max_turns": max_turns,
                    "timeout_seconds": message_timeout,
                },
                events_path=events_path,
                secrets=secrets,
                timeout_seconds=remaining,
            )
            finished_at = _utc_now()
            raw = frame.get("data")
            data: dict[str, Any] = raw if isinstance(raw, dict) else {}
            usage = _normalize_usage(data.get("usage"))
            cost_usd = _normalize_cost(data.get("cost"))
            record: dict[str, Any] = {
                "id": message["id"],
                "ended": data.get("ended")
                if data.get("ended") in {"natural", "cap", "timeout", "error"}
                else "error",
                "started_at": started_at,
                "finished_at": finished_at,
                "loops_started": int(data.get("loops_started") or 0),
                "loops_completed": int(data.get("loops_completed") or 0),
                "continuation_possible": bool(data.get("continuation_possible")),
            }
            if usage is not None:
                record["usage"] = usage
            if cost_usd is not None:
                record["cost_usd"] = cost_usd
            messages.append(record)
            extra_protect = (data.get("quiescence") or {}).get("protected_pids") or []
            protect_pids.update(int(pid) for pid in extra_protect)
            sid = data.get("session_id")
            if sid and str(sid) not in session_ids:
                session_ids.append(str(sid))
            if _settle_is_fatal(frame):
                valid = False
                ended = "error"
                invalid = data.get("invalid")
                settle_error = data.get("error")
                if isinstance(invalid, dict) and invalid.get("reason"):
                    error = str(invalid["reason"])
                elif isinstance(settle_error, str) and settle_error:
                    # Prompt rejection text, e.g. a missing credential.
                    error = settle_error
                else:
                    error = "prompt failed"
                return await finalize()
            for index, capture in _captures_after(plan, message["id"]):
                read = await capture_via_exec(
                    environment,
                    relative_path=str(capture["path"]),
                    max_bytes=int(capture.get("max_bytes") or 1024),
                )
                record_capture = write_host_capture(
                    dest_dir=evidence,
                    after=str(capture["after"]),
                    index=index,
                    relative_path=str(capture["path"]),
                    read=read,
                )
                captures.append(record_capture)
                if record_capture["status"] == "error":
                    valid = False
                    ended = "error"
                    error = "capture failed"
                    return await finalize()
            if not _may_continue(data):
                ended = record["ended"]
                # An unrecoverable message with scheduled turns left is
                # infrastructure failure, not successful retention. A
                # fully delivered script ending this way is legitimate.
                if message["id"] != script[-1]["id"]:
                    valid = False
                    error = error or f"{ended} left scheduled messages undelivered"
                break
        else:
            ended = messages[-1]["ended"] if messages else "natural"
        return await finalize()
    except asyncio.CancelledError:
        valid = False
        ended = "error"
        error = "cancelled"
        try:
            await finalize()
        except Exception:
            pass
        raise

    except Exception:
        valid = False
        ended = "error"
        error = error or "controller failure"
        try:
            await finalize()
        except Exception:
            pass
        raise


async def _await_driver(factory: Callable[[], Any]) -> DriverSession:
    created = factory()
    if inspect.isawaitable(created):
        created = await created
    return created


async def run_cold_capped_episodes(
    *,
    environment: Any,
    logs_dir: Path,
    instruction: str,
    model: str,
    episode_plan: dict[str, Any],
    max_turns: int,
    driver_factory: Callable[[], Any],
    env: dict[str, str] | None = None,
    final_cleanup: FinalCleanupFn | None = None,
    task_dir: Path | None = None,
    verify_between: Callable[..., Awaitable[float | None]] | None = None,
) -> dict[str, Any]:
    count = int(episode_plan["max"])
    extras = list(episode_plan.get("instructions") or [])
    timeout = int(episode_plan.get("timeout_seconds") or 30)
    summaries: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    to_resolution: int | None = None
    # `logs_dir` is Harbor's mounted agent directory, so per-episode
    # private evidence must live under the trial-private sibling; only
    # the relay summary and instruction stay agent-visible.
    episodes_dir = logs_dir / "episodes"
    private_episodes_dir = evidence_dir(logs_dir) / "episodes"
    # `write_relay_summary` runs in `finally` so a failing driver or a
    # raising verifier still leaves the completed episodes in the
    # relay-level evidence the host importer consumes, matching
    # `run_jsonl_episodes`.
    try:
        for index in range(1, count + 1):
            text = instruction if index == 1 else extras[index - 2]
            episode_dir = episodes_dir / f"{index:03d}"
            episode_dir.mkdir(parents=True, exist_ok=True)
            episode_logs = private_episodes_dir / f"{index:03d}" / "agent"
            episode_logs.mkdir(parents=True, exist_ok=True)
            (episode_dir / "instruction.md").write_text(text, encoding="utf-8")
            plan = {
                "mode": "single",
                "max_turns": max_turns,
                "message_timeout_seconds": timeout,
                "timeout_seconds": timeout,
            }
            started_at = _utc_now()
            summary = await run_controlled_omp(
                environment=environment,
                logs_dir=episode_logs,
                instruction=text,
                model=model,
                plan=plan,
                env=env,
                driver=await _await_driver(driver_factory),
                final_cleanup=final_cleanup,
            )
            finished_at = _utc_now()
            summaries.append(summary)
            ended = str(summary.get("ended") or "error")
            if ended not in {"natural", "cap", "timeout", "error"}:
                ended = "error"
            record = episode_helpers.episode_record(
                index=index,
                ended=ended,
                started_at=started_at,
                finished_at=finished_at,
                usage=summary.get("usage")
                if isinstance(summary.get("usage"), dict)
                else None,
                cost_usd=summary.get("cost_usd")
                if isinstance(summary.get("cost_usd"), (int, float))
                else None,
            )
            records.append(record)
            if not summary.get("valid") or ended == "error":
                break
            if (
                verify_between is not None
                and episode_plan.get("verify_between")
                and index < count
                and to_resolution is None
            ):
                reward = await verify_between(index, episode_dir)
                if reward is not None:
                    record["reward"] = reward
                    if reward >= 1.0:
                        to_resolution = index
            if to_resolution is not None:
                break
    finally:
        if records:
            episode_helpers.write_relay_summary(episodes_dir, records, to_resolution)
    # Totals span every episode that ran, and stay unknown unless every
    # episode reported the key: the last episode alone is not the trial.
    totals: dict[str, int] = {}
    total_keys: set[str] | None = None
    total_cost: float | None = None
    cost_known = bool(summaries)
    for item in summaries:
        item_usage = item.get("usage")
        keys: set[str] = set()
        if isinstance(item_usage, dict):
            for key, value in item_usage.items():
                if isinstance(value, int) and not isinstance(value, bool):
                    totals[key] = totals.get(key, 0) + value
                    keys.add(key)
        total_keys = keys if total_keys is None else (total_keys & keys)
        item_cost = item.get("cost_usd")
        if isinstance(item_cost, (int, float)) and not isinstance(item_cost, bool):
            total_cost = (0.0 if total_cost is None else total_cost) + float(item_cost)
        else:
            cost_known = False
    return {
        "schema": SCHEMA,
        "mode": "single",
        "valid": all(item.get("valid") for item in summaries),
        "episodes": summaries,
        "ended": summaries[-1]["ended"] if summaries else "error",
        "usage": {
            key: value for key, value in totals.items() if key in (total_keys or set())
        },
        "cost_usd": total_cost if cost_known else None,
    }
