# OMP and Codex Harness Expansion Plan

**Source:** plane:YACHT-3

This plan sequences the work in
[OMP and Codex harness integration](../specs/omp-codex-harness-integration.md)
against what Yacht already ships. The handoff is the outcome and
acceptance contract. This document is the implementation order.

Status: implemented in Yacht 0.11.0. Motif is the first demanding
consumer, not a Yacht-core special case.

## Product priority

A Motif-style skill claim must be runnable on OMP and Codex the same way
it already runs on Claude Code: same custom-eval task, stock versus
skill-rigged vessels, delivery evidence that does not guess, and — once
slice 6 lands — a two-episode cold relay in one workspace.

Declared harnesses stay for one-object native JSON. OMP and Codex emit
JSONL event streams, so they need thin first-class adapters.

## 0.10.0 baseline

First-class harnesses: `pi`, `claude-code`, `local-smoke`. Declared
harnesses (ADR 0016/0017) map one JSON object through dotted paths.
Harbor agents: `YachtPi`, `YachtClaudeCode`, `YachtDeclared`.

Already in place, so this expansion is not a green field:

| Need | Where it lives |
| --- | --- |
| Adapter protocol (prompt + task) | `yacht.harnesses.registry.HarnessAdapter` |
| JSONL parsers that degrade to unmeasured | `yacht.harnesses.pi`, `yacht.harnesses.claude_code` |
| Harbor job dispatch | `HARBOR_AGENT_BY_HARNESS` in `courses/terminal_bench/job.py` |
| Install-only and agent-prompt preflight | `yacht.preflight` |
| Episodic cold loop | `YachtClaudeCode`, `YachtDeclared`; Pi rejected at job render |
| Binary delivery verdict | `delivered` / `not-delivered` / `unmeasured` on the scorecard |
| Skill A/B example | `examples/custom-eval-skill-ab-smoke.toml` |

Built-in names reserved against declarations:
`{"claude-code", "local-smoke", "pi"}`. `omp` and `codex` join that set.

## What is not in front of this

These look like backlog but must not delay adapters:

- July audit follow-ups and artifact-contract integrity (closed in 0.9.0).
- ADR 0022 / 0024 / 0025 (shipped). Docs that still call them next work
  are stale.
- `yacht doctor`, run-index, configured-harness smoke.
- Pi episodic support. Motif starts on one-shot Pi. OMP and Codex need
  their own loops; Pi can follow.
- Remaining unexecuted rigging methods (`binary`, `container-image`,
  prompt pack, env var).
- Schema-file-first validation, run-index expansion, the aggregate
  text/markdown delivery column.
- Declared-harness wrappers for OMP or Codex. The handoff rejects that
  path: wrappers become untracked treatment.

## The actual prerequisite

Skill install and measurement are Claude Code conventions today.

- Tool kind `agent-skill` already exists. It is **not** an install
  method. `RIGGING_INSTALL_METHODS` has no `skill` / `agent-skill` entry.
- The shipped example installs with `method = "config-file"` and
  `target = ".claude/skills/<name>/SKILL.md"`.
- Harbor trial synthesis recognizes skills only through that path
  (`_SKILL_INSTALL_TARGET` in `attempts_from_trials.py`).
- Delivery is a binary match of `Skill:<name>` in Claude session JSONL.
- There is no `available` → `selected` → `loaded` progression.

The handoff forbids making `.claude/skills` the generic skill-install
contract and forbids treating a generic `read` as skill delivery. If
OMP and Codex adapters land first, they will grow another Claude-shaped
special case.

Slice 0 lands that contract. Slices 1–7 implement OMP and Codex against
it. Claude Code keeps working: its current `config-file` example remains
valid as a Claude-specific encoding; new configs use the logical skill
install.

Pi skill layout is out of scope. Motif's one-shot Pi path does not need
it, and this expansion does not invent one.

## Agreed order

0. Neutral skill install rendering and staged delivery evidence.
1. Native JSONL parser fixtures and pure parser tests for OMP and Codex.
2. Single-shot prompt and task adapters with version/provenance capture.
3. Map native skill events onto the slice-0 stages.
4. Install-only and agent-prompt preflight coverage.
5. Harbor agents, isolated runtimes, and one token-free or minimal-token
   smoke per harness.
6. Episodic cold execution and per-episode evidence.
7. Pinned factorial course and report comparability.

Slice 0 is the only hard gate. 1 and 2 can start once 0's artifact
shape is written down, even if Claude's migration is still in flight.
3 depends on both. 4–6 follow the existing Claude/declared patterns.
7 is the live check, not a design debate.

## Slice 0 — Neutral skill install and staged delivery

### Decision

`agent-skill` stays a tool kind only. Installation is still an
`[[riggings.*.install]]` step, so add a typed method `skill` to
`RIGGING_INSTALL_METHODS`. That is the MCP precedent: `mcp-server` is
the method; the tool's kind is separate. The step names the skill and
carries its content; each first-class adapter (Claude Code, OMP, Codex)
renders the native project-scoped layout. No Pi layout.

```toml
[tools.team-conventions]
kind = "agent-skill"
install_methods = ["skill"]

[[riggings.team-conventions-skill.install]]
method = "skill"
target = "team-conventions"
content = """
---
name: team-conventions
description: ...
---
# ...
"""
```

Claude Code's adapter writes `.claude/skills/<name>/SKILL.md`. OMP and
Codex adapters write whatever their project skill surface requires.
Harbor job rendering must call that hook rather than forwarding a
Claude path as a generic `config-file` step.

Existing `config-file` installs that already point at
`.claude/skills/.../SKILL.md` stay valid and keep producing
`Skill:<name>` expectations on Claude Code. Do not require the example
to migrate in the same change; migrate it when the OMP/Codex smokes
need a shared logical skill.

### Delivery stages

Preserve native evidence and map it to:

1. `available` — present in harness discovery
2. `selected` — harness or model chose the named skill
3. `loaded` — instructions were inserted or read
4. `unmeasured` — native evidence absent

Missing evidence stays `unmeasured`. A passing task never implies
`loaded`. A generic `read` of a skill file is not `loaded` unless the
harness records that the skill body was the thing read.

Claude Code's current parser only emits `Skill:<name>` from the Skill
tool-use input (`_qualified_tool_call`). That is `selected`. It is not
`loaded`: the parser never inspects a tool result or other insertion
evidence. `loaded` stays `unmeasured` on Claude Code until a later
change preserves separate insertion evidence. OMP `skill-prompt` is
likewise `selected` unless the event itself shows the skill body was
inserted. Codex mapping is discovered in slice 1 from real fixtures,
not assumed here.

### Artifact shape

Grow optional fields. Do not break the existing comparison
`delivery.status` vocabulary (`delivered` / `not-delivered` /
`unmeasured`).

- Attempts already carry `tool_expectations` and observed `tool_calls`.
  Add an optional per-skill stage record derived from native events,
  not from outcome.
- Scorecard `tool_invocations` stays the invocation-rate surface.
  For `kind = "agent-skill"`, "invoked" means the skill reached
  `loaded` when that stage is measured, else `selected` when only
  selection is measured. Document the rule next to the matcher in
  `task_attempt_scorecard._invoked`.
- Reports must be able to show available / selected / loaded / outcome
  as distinct facts. Outcome stays the verifier result.

Unrecognized transcripts still degrade to unmeasured, never to a wrong
count (ADR 0019).

### Files

- `src/yacht/contracts/schemas.py` — add `skill` to
  `RIGGING_INSTALL_METHODS`; optional skill-stage fields on attempts
- `src/yacht/runtimes/capabilities.py` — allow `skill` on harbor /
  container / host-nix the way `config-file` is allowed
- `src/yacht/runtimes/rigging_setup.py` and
  `containers/harbor-launcher/yacht_harbor_agents/rigging.py` — do not
  treat `skill` as a raw file write
- `src/yacht/courses/terminal_bench/job.py` — adapter-rendered skill
  steps in `rigging_steps`
- `src/yacht/courses/terminal_bench/attempts_from_trials.py` — stop
  requiring `_SKILL_INSTALL_TARGET` as the only way to know a skill
  was installed
- Tests around `tests/test_skill_invocation.py` and
  `tests/test_harbor_agent_rigging.py`

Claude Code behavior and existing artifact schemas remain compatible.

## Slice 1 — Native JSONL parsers

Pure functions, fixtures from real CLI output, no subprocess.

OMP: `omp -p --mode json --no-session ...`
Codex: `codex exec --json --ephemeral ...`

Each parser must recover, or explicitly mark unmeasured:

- final response and process exit
- input, output, cache-read, cache-write tokens when present
- cost when present, else unreported (not `$0.00`)
- model, provider
- tool calls with native names and counts
- session or turn termination reason
- skill-stage events when the stream has them

A malformed or incomplete stream fails or degrades explicitly. Follow
Pi (`tool_calls_from_pi_jsonl` → `None` vs empty tuple) and Claude
Code (`tool_calls_from_session_transcript`).

Land fixtures under `tests/` next to the parser module. Capture at
least: success with usage, success with no usage, tool-use turn,
skill-stage event if the CLI emits one, truncated stream, non-JSONL
garbage.

Do not invent Codex skill events. If the captured stream has none,
the parser's skill result is `unmeasured` and slice 3 records that.

## Slice 2 — Single-shot adapters

Copy the Pi / Claude Code shape in `src/yacht/harnesses/`:

- `OmpAdapter` / `CodexAdapter` with prompt launcher and task launcher
- argv from `command_prefix + runtime.command`, prompt as the CLI
  already expects
- transcript artifact keeps the native stream plus normalized evidence
- `usage_source` is `reported` or `unreported`, never a silent estimate
- pin and capture CLI version; record model, provider, argv

Register in `_HARNESS_ADAPTERS` and `BUILT_IN_HARNESS_NAMES`.

Approvals disabled only inside the isolated runtime. Claude Code's
container-only permission-bypass rule is the precedent if either CLI
needs an equivalent flag.

Yacht-run courses (SWE-bench, LiveCodeBench) work once the adapter
implements `task_agent`. Harbor comes in slice 5.

## Slice 3 — Skill evidence on the new parsers

Wire slice-1 skill events into slice-0 stages.

- OMP `skill-prompt` is native evidence of selection; promote to
  `loaded` only when the event shows the skill body was inserted.
- Codex: map whatever slice 1 actually captured. No fixture, no stage.
- Claude Code's `Skill:<name>` maps to `selected` only. Do not promote
  it to `loaded` without separate insertion evidence.

`_tool_expectations` for `kind = "agent-skill"` must key on the
logical skill name from the `skill` install (or the surviving Claude
`config-file` path), not on a hardcoded `.claude/skills` regex alone.

## Slice 4 — Preflight

Mostly wiring. Each new runtime recipe should prove, before task
tokens:

- binary present at the pinned version
- model/provider credentials inject
- skill discovery sees a rigged `skill` (install-only can prove the
  file landed; agent-prompt proves the harness lists or loads it)
- workspace is writable

Reuse `install-only` and `agent-prompt`. Do not add a new preflight
kind unless those two cannot express skill discovery.

## Slice 5 — Harbor agents and runtimes

- `YachtOmp` and `YachtCodex` in
  `containers/harbor-launcher/yacht_harbor_agents/agents.py`
- entries in `HARBOR_AGENT_BY_HARNESS`
- isolated install: no user-home copy, declared secrets only
- pin `harness_version` on the runtime recipe; capture the resolved
  version in provenance the way Claude Code does
- container runtime images under `containers/`, same pin style as
  `containers/claude-code-runtime` (build-arg version, non-root user,
  entrypoint-neutral)
- Harbor install may follow Harbor's installed-agent base if one
  exists for that CLI; otherwise install the pinned package the way
  `YachtPi` overrides Harbor's stale Pi package

One token-free or minimal-token smoke per harness. Install-only is
the token-free bar. A one-prompt agent-prompt check is acceptable if
skill discovery cannot be proven without it.

Rebuild and re-pin the harbor-launcher image; `yacht doctor` must see
the new runtime images when a config names them.

## Slice 6 — Episodic cold loop

Reuse ADR 0025. The host already renders the episode plan and embeds
it in the job. The new agents grow a `run()` loop like
`YachtClaudeCode._run_episodes`:

- episode 1 gets the task instruction; later episodes get only their
  declared continuation
- each episode is a fresh CLI process; no native session resume
  (`--no-session` / `--ephemeral` stay on)
- files are the only continuity channel
- per-episode native transcripts and usage under `episodes/00k/`
- Yacht wall-clock backstop plus a documented native turn cap if the
  CLI has one
- one relay remains one statistical observation

Hitting a cap or timeout is a normal episode ending. A harness crash
aborts the trial and keeps the episodes recorded so far.

Job render should accept episodic tasks on `omp` and `codex` the way
it accepts them on `claude-code` and declared harnesses. Keep the Pi
rejection until someone owns `YachtPi.run`.

## Slice 7 — Factorial course and report check

Same custom-eval task content Motif can already run on Pi:

| Harness | Control | Treatment |
| --- | --- | --- |
| Codex | stock | harness + skill |
| OMP | stock | harness + skill |

Primary estimate: treatment effect within each harness. Compare those
effects; do not treat the raw OMP-versus-Codex outcome delta as the
skill effect.

Hold course digest, prompt, permissions, runtime resources, and
episode budget. Hold model/provider where both CLIs accept the same
one. If they do not, use a connected design (OMP+Codex on one OpenAI
model; OMP+Claude Code on one Anthropic model) and record the
limitation in provenance.

Verify against the handoff acceptance list: malformed streams do not
count as measured; stock and skill-rigged vessels run the same task;
reports distinguish skill stages from outcome; tool and usage totals
trace to preserved native events; a two-episode cold relay works; Pi
and Claude Code artifacts still validate.

## Comparison and Motif

Motif can start now on one-shot Pi. It does not wait on this plan.
Once slices 2 and 5 exist, the same task directory runs on OMP and
Codex. Approval and continuity relays wait on slice 6.

Relay-specific analytics (ramp cost, rediscovery counts) stay in
Motif, built on the preserved transcripts. Yacht ships the evidence
and the generic mechanism only.

## Out of scope

- Motif-specific scoring or approval-boundary logic in Yacht core
- Native session resume as a continuity channel
- Inferring skill load from a successful verifier
- A Pi skill layout or making Pi episodic
- Broadening declared-harness `evidence_map` to JSONL
- Plugin / entry-point adapter discovery

## Acceptance (from the handoff)

- A malformed or incomplete native stream fails or degrades
  explicitly; it is never silently counted as measured evidence.
- Stock and skill-rigged vessels can run the same custom-eval task.
- Reports distinguish skill availability, selection, loading, and
  outcome.
- Tool and usage totals can be traced back to preserved native events.
- OMP and Codex can execute a two-episode cold-session relay in one
  workspace.
- Existing Pi and Claude Code behavior and artifact schemas remain
  compatible.
