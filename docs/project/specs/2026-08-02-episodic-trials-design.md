# Episodic Trials — Design

**Outcome:** plane:YACHT-1

Date: 2026-08-02
Status: approved (brainstorm walkthrough, all sections); implemented in Yacht 0.10.0
ADR: docs/adr/0025-run-episodic-trials-in-a-persistent-task-workspace.md
Plan: plans/2026-08-02-episodic-trials.md

The enabling mechanism for multi-session relay evals: one Harbor trial,
one persistent environment, the pinned agent invoked up to N times cold.
Yacht ships only the generic mechanism; concrete relay evals live in a
separate evals repo as custom-eval task directories.

## Vocabulary and hierarchy

```
run / repetition   (ADR 0021/0023 — independent fresh runs, statistics)
  └─ task
      └─ trial     (one Harbor trial: one container + workspace)
          └─ episode   (NEW — cold harness invocation, same workspace)
```

A repetition of an episodic task is a complete fresh relay. One trial
contributes exactly one paired outcome regardless of episode count;
episode metrics never enter the sign test or repetition budgets.

## Authoring surface (task directory)

```
my-relay-task/
  task.toml          # gains [episodes]
  instruction.md     # episode 1 prompt, unchanged role
  episodes/
    002.md           # episode 2 prompt — first delta
    003.md
  environment/...
  verifier/...
```

```toml
[episodes]
max = 6                        # required; >1 activates episodic mode
verify_between = true          # optional, default false
continue_instruction = "..."   # optional; yacht default documented:
                               # "Continue work on the project."
max_turns = 40                 # optional per-episode harness-native cap
timeout_seconds = 1800         # optional wall-clock backstop per episode
```

Semantics:

- Episode 1 gets the task's normal instruction, delivered as today.
- Episode k ≥ 2 gets `episodes/00k.md` alone if present, else
  `continue_instruction`. Never a union — drip-feed by construction.
- Numbering gaps (002 + 004, no 003) are a validation error at
  job-render time, host-side, before any container starts.
- No `[episodes]` table or `max = 1` → task runs exactly as today.
- Knobs + deltas live in the task dir → covered by the ADR 0015
  content digest; comparator arms run identical relays by construction.
- Deltas are read launcher-side from the mounted task dir and injected
  per episode. Never baked into the task image: episode 5's
  requirements must not be readable from inside the container during
  episode 1.

## Episode loop (yacht-owned agent run phase)

Lives in `containers/harbor-launcher/yacht_harbor_agents/agents.py`.
Harbor contract untouched: one trial, one install(), one run(), one
final verifier, one result.json.

```
run(instruction, environment, context):
    plan = episode plan (instruction 1 = Harbor's instruction; deltas +
           knobs from mounted task dir; dataset root via agent kwargs,
           task name from trial context)
    if not episodic: delegate to today's single-shot path
    for k in 1..max:
        write logs_dir/episodes/00k/instruction.md
        invoke harness COLD (fresh process, no --resume/--continue)
          with episode k's prompt
          harness-native cap: claude-code --max-turns; declared
          harnesses via a {max_turns} placeholder in their command
          (a declared command without the placeholder cannot enforce
          the cap — the timeout backstop still applies; documented)
          wall-clock backstop: asyncio timeout on the exec
        capture under logs_dir/episodes/00k/: stdout/stderr, session
          transcripts for that episode, usage snapshot, ended reason
        if verify_between and k < max:
            reward = mirror Harbor's verifier protocol against the live
                     environment (upload, exec, parse reward, remove)
            record verdict; if reward >= 1.0: break
    accumulate usage across episodes into context
```

- "Cold" = fresh harness process. Container, workspace, installed
  tools, running services, and anything the harness persisted on disk
  all survive between episodes. Files are the only memory.
- Episode ending reasons: `natural | cap | timeout | error`. Hitting
  the cap is a normal ending (forced incompleteness is the design
  working). A harness crash mid-relay = trial error, episodes so far
  preserved.
- Harness scope v1: `YachtClaudeCode` gains a run() override that
  delegates to Harbor's inherited run() for single-shot tasks;
  `YachtDeclared` extends its existing run(); `YachtPi` raises a clear
  error on episodic tasks. Episodic task + non-looping agent = trial
  error, never a silent single-shot run.
- Implementation risk to verify against pinned Harbor 0.20.0 source
  (inside the launcher image; harbor is not importable on the host):
  the exact hook for task name/dir at run() time. Confined to the thin
  agent module per ADR 0012.

## Inter-episode verification (opt-in)

- `verify_between = true` is the author's declaration that the task's
  verifier is side-effect-free. Yacht uploads verifier files, execs,
  parses reward, removes uploads (hygiene, not a guarantee). Contract
  documented in docs/reference/custom-evals.md.
- Buys: early stop on reward ≥ 1.0 (episodes_to_resolution
  measurable); per-episode reward trajectory in evidence.
- Final Harbor-run verifier remains grading truth. Mid-trial pass +
  final fail is preserved as a visible mismatch, never resolved in
  yacht's favor.
- `verify_between = false`: no mid-trial verification at all; relay
  runs to max; episodes_to_resolution absent, not fabricated.

## Artifacts, metrics, statistics

- Per-episode evidence rides logs_dir → preserved trial dir; no Harbor
  schema change. `episodes/00k/` holds instruction.md, stdout/stderr,
  session transcripts (claude-code session JSONL per episode so
  ADR 0019-style mining works per episode), usage, ended reason,
  mid-trial verdict when run.
- Optional `episodes` substructure in three places:
  - trial summary (`harness.py:_trial_summary`)
  - machine evidence (`attempts_from_trials.py:_machine_evidence`)
  - task-attempt schema `yacht.task-attempt.v1` — explicitly validated
    block (count, per-episode usage/ended/reward,
    episodes_to_resolution when measurable), alongside a new
    `_validate_task_attempt_episodes`.
- Attempt `metrics.tokens`/cost sum across episodes
  (`attempts_from_trials.py` usage aggregation).
- Absent for non-episodic trials; old artifacts stay valid.
- Statistics guardrail (stated as a rule in the ADR): one trial → one
  paired outcome. Episode numbers are descriptive evidence only.
- Relay-specific analytics (ramp cost per episode, re-discovery
  counts) stay in the evals repo, built on preserved transcripts.

## Implementation seams (from exploration, 2026-08-02)

| Concern | Where |
|---|---|
| Episode loop | `containers/harbor-launcher/yacht_harbor_agents/agents.py` (+ image rebuild, re-pin `harness.py:14`) |
| Episode-plan pure helpers | new no-harbor-import module mirroring `declared_support.py` (unit-tested from yacht repo) |
| [episodes] parse/validation | task.toml read + job-render validation; `src/yacht/courses/terminal_bench/job.py`, validator `src/yacht/contracts/schemas.py` |
| Job → Harbor config | `src/yacht/courses/terminal_bench/harness.py:145-182` (agent kwargs carry dataset root / episodic flag) |
| Read episodes back | `harness.py:288-321` collect_trial_results/_trial_summary |
| Attempt record + metrics | `attempts_from_trials.py:105,390,434` |
| Attempt schema | `contracts/schemas.py` (~1623, 2421, 2483) |
| Keep out of stats | `reports/benchmark_aggregate.py`, `reports/statistics.py` |
| Docs | `docs/reference/custom-evals.md`, new ADR 0025 |

## Testing / validation

- Pure helpers unit-tested host-side (no harbor import), fixtures
  shaped like real production output (standing lesson: complete
  fixtures, don't loosen contracts).
- Job-render validation tests for malformed relays (gaps, max < 2 with
  deltas present, etc.).
- Minimal two-episode smoke task in yacht's examples (the at-most-
  minimal example the repo split allows).
- Live token-spending relay run before release (standing pre-release
  agreement); token-free validation (install-only preflight, schema
  checks) first.

## Out of scope

- pi episodic support (errors clearly for now).
- Report/dashboard rendering beyond carrying the episodes block
  (renderers that ignore it lose only episode diagnostics).
- Any relay-eval content: tasks, comparator riggings, framework
  instantiations — all in the separate evals repo.
