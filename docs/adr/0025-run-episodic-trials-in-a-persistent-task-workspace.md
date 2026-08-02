# ADR 0025: Run Episodic Trials in a Persistent Task Workspace

## Status

Accepted

## Context

Every course YACHT runs today invokes the agent exactly once per trial:
Harbor builds the task container, the yacht-owned agent's run phase
executes the harness against the instruction, and the verifier grades
what remains. That shape cannot express a class of claims the project
exists to measure — claims about institutional memory. Session-handoff
frameworks, memory files, and context-documentation tooling all promise
the same thing: an agent that returns to a project cold does less
rediscovery and absorbs change more cheaply. Testing that promise
requires the thing the single-invocation model forbids: several cold
sessions against one evolving workspace, where the only carrier between
sessions is what the previous session left on disk.

The existing multiplicity machinery does not serve this. Repetitions
(ADR 0021, ADR 0023) are independent fresh runs for statistical power —
new container, new workspace, no shared state — the opposite of a
relay. Harbor's own `n_attempts` likewise starts fresh containers, and
YACHT's report translation rejects more than one trial per task.
Nothing in yacht enforces any budget today, and the verifier is
Harbor's alone, run once after the trial; yacht has no handle on it
mid-trial.

What the foundation does provide is the seam. ADR 0012 put yacht-owned
agent classes inside the trial: their `run()` executes launcher-side
against a live, persistent environment, and their `logs_dir` lands
inside the preserved trial directory. ADR 0015 made user-authored
task directories the authoring surface, pinned by content digest.
Multi-session evals need only a loop inside that seam — not a new
runner, not Harbor changes.

## Decision

We will let a task declare an episodic trial: the yacht-owned agent
invokes the harness up to N times cold, inside one Harbor trial,
against one persistent environment.

- **The task directory is the authoring surface.** An `[episodes]`
  table in `task.toml` activates the feature (`max` > 1) and carries
  the knobs: an optional `verify_between` flag, an optional
  `continue_instruction`, an optional per-episode `max_turns` cap and
  `timeout_seconds` backstop. Episode 1 receives the task's normal
  instruction; episode k ≥ 2 receives `episodes/00k.md` alone if it
  exists, else the continuation instruction — never a union, so
  drip-fed requirement schedules are expressible. Gaps in the delta
  numbering are validation errors at job-render time, host-side,
  before any container starts. Tasks without the table run exactly as
  today. Because knobs and deltas live in the task directory, the
  ADR 0015 content digest pins the whole relay script, and comparison
  arms run identical relays by construction.
- **The loop lives in the yacht-owned agent's run phase.** Harbor's
  contract is untouched: one trial, one `install()`, one `run()`, one
  final verifier, one result. Inside `run()`, the agent reads the
  episode plan from the mounted task directory and invokes the harness
  cold per episode — a fresh harness process, no session resumption —
  while the container, workspace, installed tools, and running
  services persist. Files are the only memory between episodes.
  Deltas are read launcher-side and injected per episode; they are
  never baked into the task image, so a future episode's requirements
  are not discoverable from inside the container.
- **Budgets are harness-native with a wall-clock backstop.** The
  per-episode cap is the harness's own limiter — `--max-turns` for
  claude-code, a placeholder declared harness commands may consume —
  so a capped episode ends the way real sessions end, with transcripts
  intact. The driver adds a timeout for hangs. Hitting the cap is a
  normal episode ending, recorded as such; forced incompleteness is
  the design working, not a failure. A harness crash mid-relay is a
  trial error that preserves the episodes recorded so far.
- **Inter-episode verification is opt-in and never grading truth.**
  With `verify_between`, the driver mirrors Harbor's verifier protocol
  against the live environment between episodes: upload, exec, parse
  the reward, remove what was uploaded. The flag is the task author's
  declaration that the verifier is side-effect-free; the documented
  contract owns the leakage risk. A passing reward ends the relay
  early, making episodes-to-resolution measurable, and every episode
  boundary gains a reward sample. The final Harbor-run verifier still
  produces the trial's grade; a mid-trial pass contradicted by the
  final verdict is preserved as a visible mismatch, never resolved in
  yacht's favor.
- **Episodes are evidence, not extra observations.** Per-episode
  artifacts — delivered instruction, harness output and session
  transcripts, usage, ending reason, mid-trial verdicts — land under
  `episodes/00k/` in the agent log directory, inside the preserved
  trial directory. The trial summary, the attempt's machine evidence,
  and the task-attempt schema gain an optional validated `episodes`
  substructure; attempt metrics sum usage across episodes. The
  statistical rule is absolute: one trial contributes exactly one
  paired outcome regardless of episode count. Episodes are
  within-trial, maximally correlated; they never enter the ADR 0023
  sign test and never count toward ADR 0021 repetition budgets. A
  repetition of an episodic task is a complete fresh relay.
- **Scope is deliberate.** Claude-code and declared harnesses loop in
  the first version; pi raises a clear error on episodic tasks until
  its run phase is owned. An episodic task on an agent that cannot
  loop is a trial error, never a silent single-shot run. Relay-specific
  analytics — ramp cost, rediscovery counting — belong to the evals
  that need them, built on the preserved transcripts; yacht ships the
  evidence and the generic mechanism only.

## Consequences

- Multi-session claims become testable with the existing foundation:
  pinned launcher, typed rigging, content-digest provenance, and
  statistics all apply to relays unchanged, and every existing task is
  untouched by the feature's absence.
- `YachtClaudeCode` must own its run phase for episodic tasks, where
  ADR 0012 preferred inheriting Harbor's. The single-shot path still
  delegates to Harbor's implementation; the divergence is confined to
  the launcher's thin agent module, and the launcher image rebuilds
  and re-pins.
- The inter-episode verifier exec is the one place yacht re-implements
  a Harbor behavior rather than consuming it. Drift surfaces as a
  recorded mismatch between mid-trial and final verdicts rather than
  as corrupted grades, because the final verdict never comes from
  yacht's exec.
- The agent needs the task's identity and directory at run time to
  read the episode plan; the exact hook into Harbor's trial context is
  verified against the pinned Harbor version during implementation and
  lives in the module ADR 0012 already designates for that coupling.
- Turn caps are not token budgets, and cap fidelity varies by harness.
  Budget calibration is the eval author's pilot work; yacht records
  per-episode usage so miscalibration is visible in evidence.
- Downstream consumers see a new optional `episodes` block in task
  attempts and native reports. Old artifacts remain valid; renderers
  that ignore the block lose nothing but episode diagnostics.
