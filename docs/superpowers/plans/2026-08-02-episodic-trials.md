# Episodic Trials (ADR 0025) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A custom-eval task can declare an episodic trial: the yacht-owned agent invokes the harness up to N times cold inside one Harbor trial against one persistent workspace, with scripted per-episode instruction deltas, harness-native caps, opt-in inter-episode verification, and per-episode evidence.

**Architecture:** The host parses and validates each task's `[episodes]` declaration at job-render time and embeds a fully resolved plan in the job's agent kwargs; the launcher-side agent classes loop over it inside Harbor's single `run()` call. Harbor's contract (one trial, one install, one run, one final verifier, one result.json) is untouched. Per-episode evidence lands under the agent `logs_dir` (`episodes/00k/`), which is inside the preserved trial directory.

**Tech Stack:** Python ≥3.12 (stdlib `tomllib`), pytest via `uv run pytest`, jj for VCS, Harbor 0.20.0 pinned inside `yacht/harbor-launcher:harbor-0.20.0`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-02-episodic-trials-design.md`; ADR: `docs/adr/0025-run-episodic-trials-in-a-persistent-task-workspace.md`.
- **Design amendment vs the spec** (verified against pinned Harbor source, approved direction): the episode plan is rendered host-side and embedded in the job document (`job["agent"]["episodes"]`, forwarded to agent kwargs), instead of the launcher re-parsing `task.toml`. One parser, render-time validation equals runtime behavior, no twin module. Deltas still never enter the task image; the content digest still pins everything (plans derive from the digested task dir).
- VCS: this repo is jj-colocated; `git commit` fails on signing. Use `jj commit -m "<message>"` after each task's steps pass. Commit messages are imperative sentences, no conventional-commit prefixes (match `jj log` style, e.g. "Render episode plans into terminal-bench jobs").
- Run tests with `uv run pytest tests/<file> -q` (or `-k` for one test). Full suite: `uv run --extra dev pytest -q` if plain `uv run pytest` lacks dev deps.
- No new dependencies. `tomllib` is stdlib on 3.12.
- Launcher-side code (`containers/harbor-launcher/yacht_harbor_agents/`) must not import `harbor` in any module that host tests load; only `agents.py` may import harbor. Host tests load launcher modules via `importlib.util.spec_from_file_location` (pattern: `tests/test_harbor_agent_rigging.py:11-20`).
- The statistical rule from ADR 0025 is absolute: one trial contributes one paired outcome regardless of episode count. Nothing in this plan may feed episode-level numbers into `reports/statistics.py` or `reports/benchmark_aggregate.py` outcome counting.
- Hand-abbreviated test fixtures fail new validators — write fixtures shaped like real production output (standing repo lesson).

## Verified Harbor 0.20.0 facts the implementation relies on

(Confirmed by reading `/usr/local/lib/python3.12/site-packages/harbor/` inside `yacht/harbor-launcher:harbor-0.20.0` on 2026-08-02. Re-verify only if the pinned image changes.)

1. `ClaudeCode.run(instruction, environment, context)` execs `claude --verbose --output-format=stream-json {flags} --print`, teeing stdout to `/logs/agent/claude-code.txt` (overwritten per invocation). `--continue` is added only when `self._resume` is truthy (default false) → repeated `super().run()` calls are cold sessions.
- `max_turns` is a declared `CliFlag` kwarg on `ClaudeCode` rendering `--max-turns N`; `BaseInstalledAgent.__init__` pops CLI-flag kwargs into `self._flag_kwargs` and resolves `self._resolved_flags = self._resolve_flag_values()`. Setting `self._flag_kwargs["max_turns"]` then re-running `_resolve_flag_values()` re-renders flags.
- `CLAUDE_CONFIG_DIR` is set to `/logs/agent/sessions` — session JSONL, todos, and pre-seeded memory persist across episodes inside the trial dir; each `claude -p` invocation creates a new session file in the same projects dir.
- The stream-json final line `{"type":"result", ...}` carries `subtype` (`"success"` / `"error_max_turns"` / other), `total_cost_usd`, and `usage` for that invocation.
- `ClaudeCode.populate_context_post_run` merges ALL session JSONL files (multi-episode → totals sum naturally), but reads cost only from the final `claude-code.txt` (last episode) — episodic cost must be summed from per-episode stream snapshots.
- A failed agent command raises `NonZeroAgentExitCodeError` (subclasses classify API errors). The claude command ends in `| tee`, so claude's own nonzero exit is usually swallowed; the `subtype` parse is the primary ended-reason signal, exception handling the fallback.
- `Trial._init_result()` writes `trial_dir/config.json` (a `TrialConfig` dump, `exclude_defaults=True`) BEFORE the agent runs; `config.json["task"]["path"]` is the local task directory for path datasets, and agent `logs_dir` is `trial_dir/agent` → the agent finds its trial dir at `self.logs_dir.parent` and its task name/dir from `config.json`.
- Trial names are `f"{task_name[:32].rstrip('_-')}__{ShortUUID}"` — truncated, so parse task identity from `config.json`, never from the dir name.
- Verifier protocol: upload the task's `tests/` dir to `/tests`, `chmod +x` the script, exec it (stdout redirected under `/logs/verifier/`), read reward from `/logs/verifier/reward.json` (`{"reward": <num>}`) or `/logs/verifier/reward.txt` (bare float). `/logs/{agent,verifier,artifacts}` are bind mounts of `trial_dir/{agent,verifier,artifacts}` for docker environments (`environment.capabilities.mounted`).
- `BaseEnvironment` has `exec(command=..., user=..., env=...)`, `upload_dir(source_dir=..., target_dir=...)`, `download_dir(source_dir=..., target_dir=...)`, `download_file(...)`.
- Harbor wraps the whole agent `run()` in the task's agent timeout (`[agent] timeout_sec` in task.toml × multiplier). Episodic tasks must set `timeout_sec` ≥ the whole relay; a Harbor-level timeout mid-relay is a trial error (honest, documented).

---

### Task 1: Host episode-plan renderer

**Files:**
- Create: `src/yacht/courses/episodes.py`
- Test: `tests/test_episode_plan.py`

**Interfaces:**
- Produces: `render_episode_plan(task_dir: Path) -> dict[str, Any] | None` raising `yacht.domain.model.ConfigError`; `DEFAULT_CONTINUE_INSTRUCTION: str`. Plan dict shape (consumed by Tasks 2, 3):

```python
{
    "max": 6,                      # int >= 2
    "verify_between": False,       # bool
    "instructions": ["...", ...],  # len == max - 1; entry i is episode i+2's prompt
    # optional:
    "max_turns": 40,               # int >= 1
    "timeout_seconds": 1800,       # int >= 1
}
```

- [ ] **Step 1: Write failing tests**

```python
# tests/test_episode_plan.py
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yacht.courses.episodes import DEFAULT_CONTINUE_INSTRUCTION, render_episode_plan
from yacht.domain.model import ConfigError


def _write_task(
    root: Path,
    *,
    episodes_table: str | None,
    deltas: dict[int, str] | None = None,
) -> Path:
    task_dir = root / "relay-task"
    task_dir.mkdir()
    body = '[metadata]\nauthor = "t"\n'
    if episodes_table is not None:
        body += episodes_table
    (task_dir / "task.toml").write_text(body, encoding="utf-8")
    (task_dir / "instruction.md").write_text("episode one\n", encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    for index, text in (deltas or {}).items():
        episodes_dir = task_dir / "episodes"
        episodes_dir.mkdir(exist_ok=True)
        (episodes_dir / f"{index:03d}.md").write_text(text, encoding="utf-8")
    return task_dir


class RenderEpisodePlanTest(unittest.TestCase):
    def test_task_without_episodes_table_is_not_episodic(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes_table=None)
            self.assertIsNone(render_episode_plan(task_dir))

    def test_max_one_is_inert(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes_table="[episodes]\nmax = 1\n")
            self.assertIsNone(render_episode_plan(task_dir))

    def test_full_plan_resolves_deltas_then_continue_instruction(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp),
                episodes_table=(
                    "[episodes]\nmax = 4\nverify_between = true\n"
                    'continue_instruction = "Keep going."\n'
                    "max_turns = 15\ntimeout_seconds = 600\n"
                ),
                deltas={2: "delta two\n", 3: "delta three\n"},
            )
            plan = render_episode_plan(task_dir)
            self.assertEqual(
                plan,
                {
                    "max": 4,
                    "verify_between": True,
                    "instructions": ["delta two\n", "delta three\n", "Keep going."],
                    "max_turns": 15,
                    "timeout_seconds": 600,
                },
            )

    def test_default_continue_instruction(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes_table="[episodes]\nmax = 2\n")
            plan = render_episode_plan(task_dir)
            self.assertEqual(plan["instructions"], [DEFAULT_CONTINUE_INSTRUCTION])
            self.assertFalse(plan["verify_between"])

    def test_delta_gap_is_an_error(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp),
                episodes_table="[episodes]\nmax = 5\n",
                deltas={2: "two\n", 4: "four\n"},
            )
            with self.assertRaisesRegex(ConfigError, "003"):
                render_episode_plan(task_dir)

    def test_delta_beyond_max_is_an_error(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp),
                episodes_table="[episodes]\nmax = 2\n",
                deltas={2: "two\n", 3: "three\n"},
            )
            with self.assertRaisesRegex(ConfigError, "max"):
                render_episode_plan(task_dir)

    def test_deltas_without_table_are_an_error(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes_table=None, deltas={2: "x\n"})
            with self.assertRaisesRegex(ConfigError, r"\[episodes\]"):
                render_episode_plan(task_dir)

    def test_unknown_key_misnamed_delta_and_bad_types_are_errors(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp), episodes_table="[episodes]\nmax = 2\nbudget = 3\n"
            )
            with self.assertRaisesRegex(ConfigError, "budget"):
                render_episode_plan(task_dir)
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(Path(tmp), episodes_table="[episodes]\nmax = 3\n")
            episodes_dir = task_dir / "episodes"
            episodes_dir.mkdir(exist_ok=True)
            (episodes_dir / "2.md").write_text("bad name\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "2.md"):
                render_episode_plan(task_dir)
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp), episodes_table="[episodes]\nmax = true\n"
            )
            with self.assertRaisesRegex(ConfigError, "max"):
                render_episode_plan(task_dir)

    def test_empty_delta_is_an_error(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp), episodes_table="[episodes]\nmax = 2\n", deltas={2: ""}
            )
            with self.assertRaisesRegex(ConfigError, "empty"):
                render_episode_plan(task_dir)

    def test_verify_between_requires_test_script(self):
        with TemporaryDirectory() as tmp:
            task_dir = _write_task(
                Path(tmp), episodes_table="[episodes]\nmax = 2\nverify_between = true\n"
            )
            (task_dir / "tests" / "test.sh").unlink()
            with self.assertRaisesRegex(ConfigError, "tests/test.sh"):
                render_episode_plan(task_dir)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests, verify they fail** — `uv run pytest tests/test_episode_plan.py -q` → import error (module missing).

- [ ] **Step 3: Implement `src/yacht/courses/episodes.py`**

```python
"""Episode-plan rendering for episodic trials (ADR 0025).

A task opts into episodic execution with an [episodes] table in its
task.toml plus optional per-episode delta files episodes/00k.md. The
plan is rendered and validated host-side at job-render time and
embedded in the terminal-bench job, so render-time validation and
runtime behavior cannot drift.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from yacht.domain.model import ConfigError


DEFAULT_CONTINUE_INSTRUCTION = "Continue work on the project."

_ALLOWED_KEYS = {
    "max",
    "verify_between",
    "continue_instruction",
    "max_turns",
    "timeout_seconds",
}
_DELTA_NAME = re.compile(r"^(\d{3})\.md$")


def render_episode_plan(task_dir: Path) -> dict[str, Any] | None:
    """The task's resolved episode plan, or None for a single-shot task.

    Raises ConfigError on any invalid declaration; validation runs
    host-side before any container starts.
    """
    table = _episodes_table(task_dir)
    deltas = _delta_texts(task_dir)
    if table is None:
        if deltas:
            raise ConfigError(
                f"{task_dir} has episodes/ delta files but no [episodes] "
                "table in task.toml"
            )
        return None
    maximum = _positive_int(table, "max", task_dir, required=True)
    if maximum == 1:
        if deltas:
            raise ConfigError(
                f"{task_dir} [episodes] max = 1 cannot carry episodes/ deltas"
            )
        return None
    _require_contiguous(deltas, maximum, task_dir)
    verify_between = table.get("verify_between", False)
    if not isinstance(verify_between, bool):
        raise ConfigError(f"{task_dir} [episodes] verify_between must be a boolean")
    if verify_between and not (task_dir / "tests" / "test.sh").is_file():
        raise ConfigError(
            f"{task_dir} [episodes] verify_between requires tests/test.sh "
            "(the inter-episode verifier mirrors the harbor test script)"
        )
    continue_instruction = table.get(
        "continue_instruction", DEFAULT_CONTINUE_INSTRUCTION
    )
    if not isinstance(continue_instruction, str) or not continue_instruction.strip():
        raise ConfigError(
            f"{task_dir} [episodes] continue_instruction must be a non-empty string"
        )
    plan: dict[str, Any] = {
        "max": maximum,
        "verify_between": verify_between,
        "instructions": [
            deltas.get(index, continue_instruction)
            for index in range(2, maximum + 1)
        ],
    }
    for key in ("max_turns", "timeout_seconds"):
        value = _positive_int(table, key, task_dir, required=False)
        if value is not None:
            plan[key] = value
    return plan


def _episodes_table(task_dir: Path) -> dict[str, Any] | None:
    config_path = task_dir / "task.toml"
    if not config_path.is_file():
        raise ConfigError(f"task directory {task_dir} is missing task.toml")
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{config_path} is not valid TOML: {error}") from error
    table = payload.get("episodes")
    if table is None:
        return None
    if not isinstance(table, dict):
        raise ConfigError(f"{config_path} [episodes] must be a table")
    unknown = sorted(set(table) - _ALLOWED_KEYS)
    if unknown:
        raise ConfigError(
            f"{config_path} [episodes] has unknown keys: {', '.join(unknown)}"
        )
    return table


def _delta_texts(task_dir: Path) -> dict[int, str]:
    episodes_dir = task_dir / "episodes"
    if not episodes_dir.is_dir():
        return {}
    deltas: dict[int, str] = {}
    for item in sorted(episodes_dir.iterdir()):
        match = _DELTA_NAME.match(item.name)
        if match is None or not item.is_file():
            raise ConfigError(
                f"{episodes_dir} entry {item.name} must be a delta file "
                "named 00k.md (three digits, episode number >= 002)"
            )
        index = int(match.group(1))
        if index < 2:
            raise ConfigError(
                f"{episodes_dir}/{item.name}: episode 1 uses instruction.md; "
                "delta numbering starts at 002"
            )
        text = item.read_text(encoding="utf-8")
        if not text.strip():
            raise ConfigError(f"{episodes_dir}/{item.name} must not be empty")
        deltas[index] = text
    return deltas


def _require_contiguous(
    deltas: dict[int, str], maximum: int, task_dir: Path
) -> None:
    if not deltas:
        return
    top = max(deltas)
    if top > maximum:
        raise ConfigError(
            f"{task_dir} episodes/{top:03d}.md exceeds [episodes] max = {maximum}"
        )
    for index in range(2, top + 1):
        if index not in deltas:
            raise ConfigError(
                f"{task_dir} episodes/ is missing {index:03d}.md; delta files "
                "must be contiguous from 002"
            )


def _positive_int(
    table: dict[str, Any], key: str, task_dir: Path, *, required: bool
) -> int | None:
    value = table.get(key)
    if value is None:
        if required:
            raise ConfigError(f"{task_dir} [episodes] must set {key}")
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(
            f"{task_dir} [episodes] {key} must be an integer >= 1"
        )
    return value
```

- [ ] **Step 4: Run tests, verify pass** — `uv run pytest tests/test_episode_plan.py -q` → all pass.
- [ ] **Step 5: Commit** — `jj commit -m "Add host-side episode-plan rendering for episodic trials"`

---

### Task 2: Render plans into the job document and gate unsupported harnesses

**Files:**
- Modify: `src/yacht/courses/terminal_bench/job.py` (render function around line 44-81)
- Modify: `src/yacht/courses/terminal_bench/harness.py:145-182` (`harbor_run_config`)
- Modify: `src/yacht/contracts/schemas.py:1279-1341` (`validate_terminal_bench_job_document`)
- Test: `tests/test_terminal_bench_course.py` (additions), `tests/test_schemas.py` (additions)

**Interfaces:**
- Consumes: `render_episode_plan` (Task 1).
- Produces: optional `job["agent"]["episodes"]: dict[str, plan]` (task id → plan dict from Task 1); `harbor_run_config` forwards it as agent `kwargs["episodes"]`. Later tasks rely on exactly these names.

- [ ] **Step 1: Write failing tests.** In `tests/test_terminal_bench_course.py`, locate the existing custom-eval job-render test (search for `render_terminal_bench_job` and `custom-eval`) and follow its fixture pattern to add:

```python
def test_render_job_embeds_episode_plans_for_episodic_tasks(self):
    # Arrange a custom-eval task dir fixture with [episodes] max=2 in
    # task.toml (reuse this file's existing task-dir fixture helper and
    # add the table + episodes/002.md), harness claude-code.
    job = render_terminal_bench_job(regatta=regatta, vessel_name=vessel)
    self.assertEqual(
        job["agent"]["episodes"][task_id]["instructions"], ["delta two\n"]
    )

def test_render_job_omits_episodes_key_when_no_task_is_episodic(self):
    job = render_terminal_bench_job(regatta=regatta, vessel_name=vessel)
    self.assertNotIn("episodes", job["agent"])

def test_render_job_rejects_episodic_tasks_on_pi(self):
    # Same episodic fixture, runtime harness "pi".
    with self.assertRaisesRegex(ConfigError, "pi"):
        render_terminal_bench_job(regatta=regatta, vessel_name=vessel)

def test_harbor_run_config_forwards_episode_plans(self):
    job = {...existing minimal job fixture..., }
    job["agent"]["episodes"] = {"relay-task": {"max": 2, "verify_between": False, "instructions": ["x"]}}
    config = harbor_run_config(job, trials_dir=Path("/tmp/trials"))
    self.assertEqual(
        config["agents"][0]["kwargs"]["episodes"]["relay-task"]["max"], 2
    )
```

In `tests/test_schemas.py`, next to the existing `validate_terminal_bench_job_document` tests, add: a valid job with `agent.episodes` passes; `max = 1` fails; `instructions` length ≠ `max - 1` fails; an episodes key not present in `job["tasks"]` fails; non-boolean `verify_between` fails.

- [ ] **Step 2: Run, verify failures** — `uv run pytest tests/test_terminal_bench_course.py -k episod -q` and `uv run pytest tests/test_schemas.py -k episod -q`.

- [ ] **Step 3: Implement.** In `job.py`:

```python
from yacht.courses.episodes import render_episode_plan  # top of file

# in render_terminal_bench_job, after `agent` is built and before `job = {...}`:
    episodes = _episode_plans(regatta.course.adapter, harness)
    if episodes:
        agent["episodes"] = episodes

# new helper:
def _episode_plans(adapter: Any, harness: str) -> dict[str, dict[str, Any]]:
    if adapter.kind != "custom-eval":
        return {}
    root = Path(str(adapter.dataset))
    plans: dict[str, dict[str, Any]] = {}
    for task_id in [str(task.id) for task in _adapter_tasks(adapter)]:
        ...
```

Note: `render_terminal_bench_job` already iterates `regatta.course.tasks` for `job["tasks"]`; pass that same list into `_episode_plans(adapter, tasks, harness)` rather than re-deriving — final signature `_episode_plans(adapter, tasks: list[str], harness: str)` called with `[str(task.id) for task in regatta.course.tasks]`. Body:

```python
    plans = {}
    for task_id in tasks:
        plan = render_episode_plan(root / task_id)
        if plan is not None:
            plans[task_id] = plan
    if plans and harness == "pi":
        raise ConfigError(
            "episodic tasks are not supported on the pi harness yet: "
            + ", ".join(sorted(plans))
        )
    return plans
```

In `harness.py` `harbor_run_config`, after the `declaration` forwarding (line ~150):

```python
    if agent.get("episodes"):
        kwargs["episodes"] = dict(agent["episodes"])
```

In `schemas.py` `validate_terminal_bench_job_document`, after the `declaration` check (line ~1332):

```python
    if "episodes" in agent:
        _validate_job_episode_plans(agent["episodes"], document["tasks"])
```

New validator beside it:

```python
def _validate_job_episode_plans(value: Any, tasks: Any) -> None:
    episodes = _require_object(value, "terminal-bench job.agent.episodes")
    task_names = {str(task) for task in tasks} if isinstance(tasks, list) else set()
    for task_name, plan_value in episodes.items():
        path = f"terminal-bench job.agent.episodes[{task_name}]"
        _require_non_empty_string(task_name, "terminal-bench job.agent.episodes key")
        if task_name not in task_names:
            raise SchemaValidationError(
                f"{path} does not match any task in the job"
            )
        plan = _require_object(plan_value, path)
        _require_keys(plan, ("max", "verify_between", "instructions"), path)
        maximum = plan["max"]
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 2:
            raise SchemaValidationError(f"{path}.max must be an integer >= 2")
        if not isinstance(plan["verify_between"], bool):
            raise SchemaValidationError(f"{path}.verify_between must be a boolean")
        instructions = _require_list(plan["instructions"], f"{path}.instructions")
        if len(instructions) != maximum - 1:
            raise SchemaValidationError(
                f"{path}.instructions must contain max - 1 entries"
            )
        for index, entry in enumerate(instructions):
            _require_non_empty_string(entry, f"{path}.instructions[{index}]")
        for key in ("max_turns", "timeout_seconds"):
            if key in plan:
                value = plan[key]
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise SchemaValidationError(
                        f"{path}.{key} must be an integer >= 1"
                    )
```

- [ ] **Step 4: Run, verify pass** — both `-k episod` selections, then `uv run pytest tests/test_terminal_bench_course.py tests/test_schemas.py -q` for regressions.
- [ ] **Step 5: Commit** — `jj commit -m "Render episode plans into terminal-bench jobs and gate pi"`

---

### Task 3: Launcher-side pure episode helpers

**Files:**
- Create: `containers/harbor-launcher/yacht_harbor_agents/episodes.py`
- Test: `tests/test_harbor_agent_episodes.py`

**Interfaces:**
- Produces (consumed by Tasks 4-6; module loaded in `agents.py` as `from yacht_harbor_agents import episodes`):
  - `ENDED_NATURAL = "natural"`, `ENDED_CAP = "cap"`, `ENDED_TIMEOUT = "timeout"`, `ENDED_ERROR = "error"`
  - `class EpisodePlanError(RuntimeError)`
  - `plan_for_task(episodes_kwarg: dict | None, task_name: str) -> dict | None` — shape-revalidates (max int ≥2, instructions list len max-1, verify_between bool); malformed → `EpisodePlanError` (a trial error, never a silent single-shot run)
  - `task_identity(trial_dir: Path) -> tuple[str, Path]` — reads `trial_dir/config.json`, returns `(task_name, task_dir)` from `["task"]["path"]` (name = `Path(path).name`); missing/malformed or non-local task (no `path` key) → `EpisodePlanError`
  - `parse_claude_stream_result(text: str) -> dict` — last `{"type": "result"}` JSON line → `{"subtype": str | None, "usage": dict | None, "cost_usd": float | None}`; usage filtered to non-negative-int values of `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`
  - `claude_episode_ended(subtype: str | None, timed_out: bool, errored: bool) -> str` — timeout wins, then `error_max_turns` → cap, then `success` and not errored → natural, else error
  - `sessions_manifest(sessions_root: Path) -> list[dict]` — `[{"path": <relative posix>, "size": <int>}, ...]` for every `*.jsonl` under `sessions_root`, sorted by path; `[]` if the dir is missing
  - `read_reward(verifier_dir: Path) -> float | None` — `reward.json` `{"reward": <num>}` first (single-key fallback like `harness.py:_trial_reward`), else `reward.txt` bare float, else/unparseable → None
  - `merged_declared_evidence(per_episode: list[dict]) -> dict` — yacht.harness-evidence.v1 doc: `response` from last episode, usage keys summed (`input_tokens`, `output_tokens` required; `cache_read_tokens` summed when every episode has it), `tool_calls` merged by name with counts summed (present only if any episode has them), `model` from the last episode that names one, `cost` `{"total_usd": sum}` only when every episode has a cost
  - `episode_record(*, index, ended, started_at, finished_at, usage=None, cost_usd=None, reward=None) -> dict` — drops None fields
  - `write_relay_summary(episodes_dir: Path, records: list[dict], to_resolution: int | None) -> None` — writes `episodes_dir/summary.json` `{"count": len(records), "items": records}` plus `"to_resolution"` when not None (indent=2, sort_keys=True, trailing newline)

- [ ] **Step 1: Write failing tests.** `tests/test_harbor_agent_episodes.py` loads the module with the `importlib.util.spec_from_file_location` pattern from `tests/test_harbor_agent_rigging.py:11-20` (path `containers/harbor-launcher/yacht_harbor_agents/episodes.py`, module name `yacht_harbor_agents_episodes`). Cover: plan_for_task happy/malformed/absent; task_identity from a temp trial dir with a real-shaped `config.json` (`{"task": {"path": "/tasks/relay-task"}, "trial_name": "relay-task__abc1234"}`) and the malformed/registry cases; parse_claude_stream_result with a realistic multi-line stream (system lines, then `{"type":"result","subtype":"error_max_turns","total_cost_usd":0.42,"usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":10,"cache_creation_input_tokens":0}}`), empty text, and no-result-line text; every claude_episode_ended branch; sessions_manifest nested files + missing dir; read_reward json/txt/missing/garbage; merged_declared_evidence sums + cost-omitted-when-partial + tool_calls merge; write_relay_summary content round-trip.
- [ ] **Step 2: Run, verify failure** — `uv run pytest tests/test_harbor_agent_episodes.py -q`.
- [ ] **Step 3: Implement the module.** Pure stdlib (`json`, `pathlib`, `re`); NO harbor imports (host tests must load it). Docstring cites ADR 0025 and notes the plan shape is produced by `yacht.courses.episodes.render_episode_plan` and validated again here defensively.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `jj commit -m "Add launcher-side episode helpers"`

---

### Task 4: Inter-episode verifier exec

**Files:**
- Modify: `containers/harbor-launcher/yacht_harbor_agents/agents.py` (new module-level coroutine)
- Test: covered by Task 3's pure helpers + Task 8's integration fixtures; the exec sequence itself is exercised in the live validation (Task 11) — keep the coroutine thin

**Interfaces:**
- Produces: `run_episode_verifier(environment, task_dir: Path, episode_dir: Path, verifier_dir: Path) -> float | None` used by Tasks 5 and 6.

- [ ] **Step 1: Implement** in `agents.py` (after `apply_rigging_steps`):

```python
async def run_episode_verifier(
    environment: BaseEnvironment,
    task_dir: Path,
    episode_dir: Path,
    verifier_dir: Path,
) -> float | None:
    """Mirror harbor's verifier protocol between episodes (ADR 0025).

    The task's verify_between flag asserts the verifier is
    side-effect-free; upload, exec, and removal are hygiene, not a
    guarantee. The reward returned here never grades the trial — the
    final harbor-run verifier remains grading truth.
    """
    tests_dir = task_dir / "tests"
    if not tests_dir.is_dir():
        raise episodes.EpisodePlanError(
            f"verify_between requires a tests directory at {tests_dir}"
        )
    await environment.upload_dir(source_dir=tests_dir, target_dir="/tests")
    await environment.exec(command="chmod +x /tests/test.sh", user="root")
    await environment.exec(
        command="/tests/test.sh > /logs/verifier/episode-stdout.txt 2>&1 || true"
    )
    if not environment.capabilities.mounted:
        await environment.download_dir(
            source_dir="/logs/verifier", target_dir=str(verifier_dir)
        )
    reward = episodes.read_reward(verifier_dir)
    episode_dir.mkdir(parents=True, exist_ok=True)
    for name in ("reward.json", "reward.txt", "episode-stdout.txt"):
        source = verifier_dir / name
        if source.is_file():
            source.rename(episode_dir / name)
    await environment.exec(
        command=(
            "rm -rf /tests /logs/verifier/reward.json "
            "/logs/verifier/reward.txt /logs/verifier/episode-stdout.txt"
        ),
        user="root",
    )
    return reward
```

Add `from yacht_harbor_agents import episodes` to the imports.

- [ ] **Step 2: Syntax-check without harbor** — `uv run python -c "import ast; ast.parse(open('containers/harbor-launcher/yacht_harbor_agents/agents.py').read())"` (agents.py imports harbor, so only parse it host-side).
- [ ] **Step 3: Commit** — `jj commit -m "Add inter-episode verifier exec to the harbor agents"`

---

### Task 5: Episodic run loop in YachtClaudeCode

**Files:**
- Modify: `containers/harbor-launcher/yacht_harbor_agents/agents.py:49-66` (`YachtClaudeCode`)

**Interfaces:**
- Consumes: everything from Tasks 3-4; verified Harbor facts 1-7 above.
- Produces: per-episode artifacts under `logs_dir/episodes/00k/` (`instruction.md`, `claude-code.txt`, `sessions-manifest.json`, verifier files when run) and `logs_dir/episodes/summary.json`; summed `context.cost_usd` for episodic trials.

- [ ] **Step 1: Implement.** Replace `YachtClaudeCode` with:

```python
class YachtClaudeCode(ClaudeCode):
    @staticmethod
    def name() -> str:
        return "yacht-claude-code"

    def __init__(
        self,
        logs_dir: Path,
        rigging_steps: list[dict[str, Any]] | None = None,
        episodes: dict[str, Any] | None = None,
        *args,
        **kwargs,
    ):
        self._rigging_steps = list(rigging_steps or [])
        self._episodes_kwarg = dict(episodes or {})
        self._episode_costs: list[float | None] = []
        super().__init__(logs_dir, *args, **kwargs)

    async def install(self, environment: BaseEnvironment) -> None:
        await super().install(environment)
        await apply_rigging_steps(environment, self._rigging_steps)

    async def run(self, instruction, environment: BaseEnvironment, context) -> None:
        plan, task_dir = self._episode_plan()
        if plan is None:
            await super().run(instruction, environment, context)
            return
        await self._run_episodes(plan, task_dir, instruction, environment, context)

    def _episode_plan(self) -> tuple[dict[str, Any] | None, Path | None]:
        if not self._episodes_kwarg:
            return None, None
        task_name, task_dir = episodes.task_identity(self.logs_dir.parent)
        plan = episodes.plan_for_task(self._episodes_kwarg, task_name)
        return plan, task_dir

    async def _run_episodes(
        self,
        plan: dict[str, Any],
        task_dir: Path,
        instruction: str,
        environment: BaseEnvironment,
        context,
    ) -> None:
        episodes_dir = self.logs_dir / "episodes"
        if plan.get("max_turns") is not None:
            self._flag_kwargs["max_turns"] = plan["max_turns"]
            self._resolved_flags = self._resolve_flag_values()
        records: list[dict[str, Any]] = []
        to_resolution: int | None = None
        failure: Exception | None = None
        for index in range(1, plan["max"] + 1):
            text = instruction if index == 1 else plan["instructions"][index - 2]
            episode_dir = episodes_dir / f"{index:03d}"
            episode_dir.mkdir(parents=True, exist_ok=True)
            (episode_dir / "instruction.md").write_text(text, encoding="utf-8")
            started_at = _utc_now()
            timed_out = False
            error: Exception | None = None
            try:
                timeout = plan.get("timeout_seconds")
                if timeout:
                    async with asyncio.timeout(timeout):
                        await super().run(text, environment, context)
                else:
                    await super().run(text, environment, context)
            except TimeoutError:
                timed_out = True
                await environment.exec(
                    command="pkill -f 'claude --verbose' || true"
                )
            except NonZeroAgentExitCodeError as exc:
                error = exc
            finished_at = _utc_now()
            result = self._snapshot_episode(episode_dir)
            ended = episodes.claude_episode_ended(
                result["subtype"], timed_out, error is not None
            )
            self._episode_costs.append(result["cost_usd"])
            record = episodes.episode_record(
                index=index,
                ended=ended,
                started_at=started_at,
                finished_at=finished_at,
                usage=result["usage"],
                cost_usd=result["cost_usd"],
            )
            if ended == episodes.ENDED_ERROR:
                records.append(record)
                failure = error or RuntimeError(
                    f"episode {index} ended in error without an exception"
                )
                break
            if (
                plan["verify_between"]
                and index < plan["max"]
                and to_resolution is None
            ):
                reward = await run_episode_verifier(
                    environment, task_dir, episode_dir, self.logs_dir.parent / "verifier"
                )
                if reward is not None:
                    record["reward"] = reward
                    if reward >= 1.0:
                        to_resolution = index
            records.append(record)
            if to_resolution is not None:
                break
        episodes.write_relay_summary(episodes_dir, records, to_resolution)
        if failure is not None:
            raise failure

    def _snapshot_episode(self, episode_dir: Path) -> dict[str, Any]:
        stream_path = self.logs_dir / "claude-code.txt"
        text = ""
        if stream_path.is_file():
            text = stream_path.read_text(encoding="utf-8", errors="replace")
            (episode_dir / "claude-code.txt").write_text(text, encoding="utf-8")
        manifest = episodes.sessions_manifest(self.logs_dir / "sessions" / "projects")
        (episode_dir / "sessions-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return episodes.parse_claude_stream_result(text)

    def populate_context_post_run(self, context) -> None:
        super().populate_context_post_run(context)
        if self._episode_costs and all(
            cost is not None for cost in self._episode_costs
        ):
            context.cost_usd = sum(self._episode_costs)
```

Imports to add at the top of `agents.py`: `import asyncio`, `from datetime import datetime, timezone`, `from harbor.agents.installed.base import NonZeroAgentExitCodeError`, and a module-level helper:

```python
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
```

Behavioral notes the implementer must preserve:
- Cap (`error_max_turns`) and timeout are NORMAL episode endings — the relay continues (forced incompleteness is the design working). Only `ended == "error"` aborts, and it aborts AFTER writing the summary, preserving episodes so far (ADR 0025).
- Harbor's own single-shot claude semantics are untouched: no `episodes` kwarg (or a non-episodic task) → exactly today's `super().run()` path.
- `self._flag_kwargs` / `self._resolve_flag_values()` are the documented touch of harbor internals; keep them inside this class with a comment citing the verified fact (CliFlag resolution, base.py) so an image upgrade re-checks it.

- [ ] **Step 2: Syntax-check** — same `ast.parse` command as Task 4.
- [ ] **Step 3: Run the full host suite for regressions** — `uv run pytest -q` (agents.py is not imported by host tests; this catches accidental cross-module breakage only).
- [ ] **Step 4: Commit** — `jj commit -m "Loop yacht-claude-code cold over episodes inside one trial"`

---

### Task 6: Episodic run loop in YachtDeclared + max_turns placeholder

**Files:**
- Modify: `containers/harbor-launcher/yacht_harbor_agents/declared_support.py:49-72` (`run_command`)
- Modify: `containers/harbor-launcher/yacht_harbor_agents/agents.py:114-234` (`YachtDeclared`)
- Test: `tests/test_harbor_agent_episodes.py` (run_command additions; load `declared_support.py` with the same importlib pattern)

**Interfaces:**
- Consumes: Tasks 3-4 helpers.
- Produces: `run_command(declaration, *, model, instruction, max_turns: int | None = None)`; per-episode `episodes/00k/{instruction.md, run-stdout.txt, run-stderr.txt, harness-evidence.json}`; merged trial-level `logs_dir/harness-evidence.json`; `episodes/summary.json`.

- [ ] **Step 1: Write failing tests** for `run_command`: `{max_turns}` in a command item is replaced with the string value when `max_turns` is set; a command containing the placeholder with `max_turns=None` raises `DeclaredAgentError`; `max_turns` set with no placeholder in the command leaves the command unchanged (the wall-clock backstop is the only cap — documented, not an error).
- [ ] **Step 2: Run, verify failure.**
- [ ] **Step 3: Implement `run_command`:** add the keyword-only parameter; substitution loop becomes

```python
    argv = []
    for item in declaration.get("command", []):
        rendered = item.replace("{model}", model)
        if "{max_turns}" in rendered:
            if max_turns is None:
                raise DeclaredAgentError(
                    f"declared harness {declaration.get('name')} command uses "
                    "{max_turns} but the task sets no per-episode cap"
                )
            rendered = rendered.replace("{max_turns}", str(max_turns))
        argv.append(rendered)
```

- [ ] **Step 4: Implement the `YachtDeclared` loop.** `__init__` gains `episodes: dict[str, Any] | None = None` (store as `self._episodes_kwarg`). Refactor `_collect_evidence(self, environment, result)` to `_collect_evidence(self, environment, result, target: Path)` writing `harness-evidence.json` into `target` (single-shot call sites pass `self.logs_dir`). `run()` becomes: resolve plan exactly as `YachtClaudeCode._episode_plan()` (share via a small module-level `def resolve_episode_plan(episodes_kwarg, logs_dir)` used by both classes); no plan → current body unchanged. With a plan, loop `1..max`:
  - build the command via `declared_support.run_command(self._declaration, model=..., instruction=text, max_turns=plan.get("max_turns"))`
  - exec with the same `asyncio.timeout` wrapper as Task 5; on `TimeoutError` → `ended="timeout"`, best-effort `pkill -f <binary_path> || true`, no evidence for that episode; on nonzero exit → write stdout/stderr to the episode dir, record `ended="error"`, write summary, raise (mirrors the single-shot error contract)
  - on success → `ended="natural"` (declared harnesses have no cap signal; documented), write `run-stdout.txt`/`run-stderr.txt` into the episode dir, collect evidence into the episode dir, `rm -f /logs/agent/harness-evidence.json` in-container so the next episode cannot inherit it, and pull `usage`/`cost` for the record from `declared_support.context_fields` of that episode's evidence
  - `verify_between` handling identical to Task 5
  - after the loop: `self._evidence = declared_support.normalize_evidence(self._declaration, episodes.merged_declared_evidence(per_episode_evidence))`... **correction**: `merged_declared_evidence` already returns a valid evidence document — validate it with `declared_support.validate_evidence` instead of re-mapping, and also write it to `self.logs_dir / "harness-evidence.json"` so post-hoc attempt mining (`attempts_from_trials._observed_tool_calls`) sees trial-level evidence; write the relay summary.
  - An episode that succeeds but yields invalid evidence is a trial error today (`_collect_evidence` raises); keep that — record `ended="error"`, summary, raise.
- [ ] **Step 5: Run tests + syntax-check** — `uv run pytest tests/test_harbor_agent_episodes.py -q` and the `ast.parse` check.
- [ ] **Step 6: Commit** — `jj commit -m "Loop declared harnesses over episodes with a max-turns placeholder"`

---

### Task 7: Trial summary carries the episodes block

**Files:**
- Modify: `src/yacht/courses/terminal_bench/harness.py:293-321` (`_trial_summary`, new `_trial_episodes`)
- Test: `tests/test_terminal_bench_course.py` (additions near existing `_trial_summary`/`collect_trial_results` tests)

**Interfaces:**
- Produces: trial summary optional key `"episodes": {"count": int, "items": [record, ...], "to_resolution"?: int}` read from `<trial_dir>/agent/episodes/summary.json`. Records are exactly what `write_relay_summary` wrote (Task 3).

- [ ] **Step 1: Write failing tests:** a trial dir fixture whose `agent/episodes/summary.json` matches production shape (write it with the same keys `write_relay_summary` produces, e.g. two items with `index/ended/started_at/finished_at/usage/cost_usd`, one with `reward`) → `_trial_summary` output contains the block verbatim under `"episodes"`; a trial dir without the file → no `"episodes"` key; a corrupt file (invalid JSON) and a wrong-shape file (`{"count": "2"}`) → no `"episodes"` key (degrade to unmeasured, matching the pi-JSONL precedent).
- [ ] **Step 2: Run, verify failure.**
- [ ] **Step 3: Implement:**

```python
# in _trial_summary, after the usage block:
    episodes = _trial_episodes(result_path.parent)
    if episodes is not None:
        summary["episodes"] = episodes


def _trial_episodes(trial_dir: Path) -> dict[str, Any] | None:
    """Relay evidence from the agent's episodes/summary.json (ADR 0025).

    Malformed evidence degrades to absent — an unreadable relay is
    unmeasured, never invented."""
    summary_path = trial_dir / "agent" / "episodes" / "summary.json"
    if not summary_path.is_file():
        return None
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    count = payload.get("count")
    items = payload.get("items")
    if not isinstance(count, int) or isinstance(count, bool):
        return None
    if not isinstance(items, list) or len(items) != count:
        return None
    episodes: dict[str, Any] = {"count": count, "items": items}
    to_resolution = payload.get("to_resolution")
    if (
        isinstance(to_resolution, int)
        and not isinstance(to_resolution, bool)
        and 1 <= to_resolution <= count
    ):
        episodes["to_resolution"] = to_resolution
    return episodes
```

- [ ] **Step 4: Run, verify pass** — `uv run pytest tests/test_terminal_bench_course.py -q`.
- [ ] **Step 5: Commit** — `jj commit -m "Carry relay episodes from trial dirs into the native report"`

---

### Task 8: Task attempts carry a validated episodes block

**Files:**
- Modify: `src/yacht/courses/terminal_bench/attempts_from_trials.py:105-151` (`_attempt_from_trial`), `:390-431` (`_machine_evidence`)
- Modify: `src/yacht/contracts/schemas.py:1623-1667` (`validate_task_attempt_document`, new `_validate_task_attempt_episodes`)
- Test: `tests/test_schemas.py`, `tests/test_custom_eval_adapter.py` (or `tests/test_task_attempts.py` — wherever `_attempt_from_trial`-path fixtures already live; follow the existing episodic-free fixture and extend it)

**Interfaces:**
- Produces: task-attempt optional top-level `"episodes"` block (same shape as Task 7's) validated by the schema; `agent.machine_evidence.episodes` carrying the same `items` list; attempt `metrics` unchanged (trial usage already aggregates the whole relay: claude-code sums merged sessions, declared sums merged evidence).

- [ ] **Step 1: Write failing tests.**
  - `tests/test_schemas.py`: a valid attempt with `episodes` `{"count": 2, "to_resolution": 2, "items": [{"index": 1, "ended": "cap", "started_at": "2026-08-02T00:00:00+00:00", "finished_at": "2026-08-02T00:10:00+00:00", "usage": {"input_tokens": 100, "output_tokens": 50}, "cost_usd": 0.4}, {"index": 2, "ended": "natural", "reward": 1.0}]}` passes; rejects: `count` ≠ `len(items)`, unknown `ended` value, `to_resolution` > `count`, negative `cost_usd`, non-object item.
  - Attempt-synthesis test: extend an existing trial fixture with the `episodes` block from Task 7 → the written attempt has `attempt["episodes"]` equal to it, `machine_evidence["episodes"] == block["items"]`, and `metrics.tokens` unchanged from the non-episodic expectation (usage is trial-level).
  - `tests/test_benchmark_aggregate.py`: an attempt artifact carrying an `episodes` block flows through aggregation identically to one without — same outcome counts (the one-trial-one-outcome guardrail pinned as a test).
- [ ] **Step 2: Run, verify failures.**
- [ ] **Step 3: Implement.**
  - `_attempt_from_trial`: after the `tool_expectations` block —

```python
    episodes = trial.get("episodes") if isinstance(trial, dict) else None
    if isinstance(episodes, dict):
        artifact["episodes"] = episodes
```

  - `_machine_evidence`: before the exception block —

```python
    episodes = trial.get("episodes")
    if isinstance(episodes, dict) and isinstance(episodes.get("items"), list):
        evidence["episodes"] = episodes["items"]
```

  - `schemas.py`: in `validate_task_attempt_document`, after the `tool_expectations` check: `if "episodes" in document: _validate_task_attempt_episodes(document["episodes"])`. New validator:

```python
_EPISODE_ENDINGS = {"natural", "cap", "timeout", "error"}


def _validate_task_attempt_episodes(value: Any) -> None:
    episodes = _require_object(value, "episodes")
    _require_keys(episodes, ("count", "items"), "episodes")
    count = episodes["count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise SchemaValidationError("episodes.count must be an integer >= 1")
    items = _require_list(episodes["items"], "episodes.items")
    if len(items) != count:
        raise SchemaValidationError("episodes.items must contain count entries")
    if "to_resolution" in episodes:
        to_resolution = episodes["to_resolution"]
        if (
            isinstance(to_resolution, bool)
            or not isinstance(to_resolution, int)
            or not 1 <= to_resolution <= count
        ):
            raise SchemaValidationError(
                "episodes.to_resolution must be an integer between 1 and count"
            )
    for index, item_value in enumerate(items):
        path = f"episodes.items[{index}]"
        item = _require_object(item_value, path)
        _require_keys(item, ("index", "ended"), path)
        item_index = item["index"]
        if isinstance(item_index, bool) or not isinstance(item_index, int) or item_index < 1:
            raise SchemaValidationError(f"{path}.index must be an integer >= 1")
        _require_allowed_value(item["ended"], _EPISODE_ENDINGS, f"{path}.ended")
        for key in ("started_at", "finished_at"):
            if key in item:
                _require_non_empty_string(item[key], f"{path}.{key}")
        if "usage" in item:
            _validate_numeric_evidence_map(item["usage"], f"{path}.usage")
        for key in ("cost_usd", "reward"):
            if key in item:
                _require_non_negative_number(item[key], f"{path}.{key}")
```

- [ ] **Step 4: Run, verify pass** — the three test files, then full suite `uv run pytest -q`.
- [ ] **Step 5: Commit** — `jj commit -m "Validate and carry a per-episode block on task attempts"`

---

### Task 9: Example relay task

**Files:**
- Create: `examples/custom-evals/relay-task/task.toml`, `instruction.md`, `episodes/002.md`, `tests/test.sh`, `solution/solve.sh`, `environment/Dockerfile`

**Interfaces:** none downstream; this is the minimal smoke relay the repo split allows (ADR 0025 scope), used by Task 11's token-free validation and any future live run.

- [ ] **Step 1: Write the task files** (modeled on `examples/custom-evals/hello-task/`):

`task.toml`:
```toml
[metadata]
author = "yacht"
description = "Smoke relay: two cold episodes against one workspace."
difficulty = "easy"

[verifier]
timeout_sec = 60.0

[agent]
# Covers the whole relay: both episodes plus inter-episode verification.
timeout_sec = 900.0

[episodes]
max = 2
verify_between = true
max_turns = 15
timeout_seconds = 300
```

`instruction.md`:
```markdown
Create a file at `/app/NOTES.md` recording, in one line each, any project
decisions you make. Then create `/app/greeting.txt` containing exactly:

```
Hello from YACHT!
```

Leave notes a future session would need to continue this project.
```

`episodes/002.md`:
```markdown
A new requirement arrived: `/app/greeting.txt` must now contain exactly:

```
Hello again from YACHT!
```

Check `/app/NOTES.md` for prior decisions, apply the change, and record it.
```

`tests/test.sh`:
```bash
#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier

if [ "$(cat /app/greeting.txt 2>/dev/null)" = "Hello again from YACHT!" ] \
    && [ -s /app/NOTES.md ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
```

Note this verifier is honestly side-effect-free (reads workspace, writes only `/logs/verifier`) — the `verify_between = true` contract. It scores 0 after episode 1 (greeting says "Hello", not "Hello again") and 1 after episode 2, so the smoke relay demonstrates a mid-relay non-resolution followed by resolution.

`solution/solve.sh`:
```bash
#!/bin/bash
set -euo pipefail
mkdir -p /app
echo "decision: greeting lives in /app/greeting.txt" > /app/NOTES.md
echo "Hello again from YACHT!" > /app/greeting.txt
```

`environment/Dockerfile`:
```dockerfile
FROM node:22-bookworm-slim

RUN mkdir -p /app
WORKDIR /app
```

- [ ] **Step 2: Prove the example passes render-time validation**

```bash
uv run python -c "
from pathlib import Path
from yacht.courses.episodes import render_episode_plan
plan = render_episode_plan(Path('examples/custom-evals/relay-task'))
assert plan['max'] == 2 and plan['verify_between'] is True, plan
print(plan)
"
```

- [ ] **Step 3: Commit** — `jj commit -m "Add a two-episode relay example task"`

---

### Task 10: Documentation

**Files:**
- Modify: `docs/reference/custom-evals.md` (new "Episodic tasks" section, placed after the task-authoring section)

- [ ] **Step 1: Write the section.** It must cover, with the `relay-task` example inline: the `[episodes]` table keys and defaults (`max`, `verify_between` default false, `continue_instruction` default "Continue work on the project.", `max_turns`, `timeout_seconds`); delta files `episodes/002.md`… contiguous from 002, episode k receives file k alone, later episodes receive the continuation instruction — never a union; the `verify_between` contract (author asserts the verifier is side-effect-free; upload/exec/removal is hygiene, not a guarantee; the final Harbor verifier remains grading truth and a mid-relay pass contradicted by the final verdict is preserved as a visible mismatch); the task's `[agent] timeout_sec` must cover the entire relay; caps are harness-native (`--max-turns` for claude-code; declared harnesses opt in with a `{max_turns}` placeholder in their declared command, without it only the wall-clock backstop applies); pi is not supported yet and fails at render time; per-episode evidence layout (`<trial>/agent/episodes/00k/`, `summary.json`) and the attempt's `episodes` block; and the statistics rule — one trial is one paired outcome, episode metrics are descriptive evidence only, a repetition is a complete fresh relay (cite ADR 0025).
- [ ] **Step 2: Check cross-references** — `grep -n "episodes" docs/reference/custom-evals.md` reads coherently; ADR 0025 path correct.
- [ ] **Step 3: Commit** — `jj commit -m "Document episodic task authoring"`

---

### Task 11: Launcher image rebuild and token-free validation

**Files:** none new (build + verification)

- [ ] **Step 1: Rebuild the launcher image** (same tag — the harbor pin is unchanged; per `docs/reference/release.md:74`):

```bash
docker build -t yacht/harbor-launcher:harbor-0.20.0 containers/harbor-launcher
```

- [ ] **Step 2: In-image import smoke** (catches harbor-API drift in agents.py without spending tokens):

```bash
docker run --rm --entrypoint python yacht/harbor-launcher:harbor-0.20.0 -c "
from yacht_harbor_agents.agents import YachtClaudeCode, YachtDeclared, YachtPi, run_episode_verifier
from yacht_harbor_agents import episodes
print('agents import ok')
"
```

- [ ] **Step 3: Full host suite** — `uv run pytest -q` → all pass (804+ tests).
- [ ] **Step 4: Install-only preflight against the relay example.** Write a scratch regatta config (scratchpad, not the repo) pointing `kind = "custom-eval"`, `dataset` at `examples/custom-evals` with the relay task selected, harness claude-code, and run yacht's install-only preflight path (see `docs/reference/custom-evals.md` for the invocation; zero token cost). Expected: preflight passes, proving agent install + rigging + job render (including the episodes kwargs) in a real task container.
- [ ] **Step 5: Commit any fixes; do NOT tag or release.** The live token-spending relay run is gated on Cody per the standing pre-release agreement — report readiness instead of running it.

---

## Self-review notes (already applied)

- Spec coverage: authoring surface (T1/T2/T9/T10), loop + cold semantics + caps (T5/T6), pi gate at render (T2), inter-episode verifier (T4), artifacts three places (T5-T8), stats guardrail as a pinned test (T8), smoke example (T9), docs (T10), image + token-free validation (T11). The spec's "launcher reads the mounted task dir" line is superseded by the embedded-plan amendment (header); `task_identity` still reads the task dir path for the verifier upload only.
- Type consistency: plan dict keys (`max`, `verify_between`, `instructions`, `max_turns`, `timeout_seconds`), summary keys (`count`, `items`, `to_resolution`), record keys (`index`, `ended`, `started_at`, `finished_at`, `usage`, `cost_usd`, `reward`), and ended values (`natural`, `cap`, `timeout`, `error`) are identical across Tasks 1-8 and the docs.
- Known accepted limits (documented in T10, not bugs): declared harnesses have no cap signal (`ended` is never `cap`); the inter-episode verifier ignores task-level `verifier.env` and assumes `tests/test.sh`; `asyncio.timeout` cancellation relies on best-effort `pkill`.
