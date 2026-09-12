# Bounded OMP Eval Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sjujperpowers:subagent-driven-development or sjujperpowers:executing-plans. Implement the tasks below; Main owns integration, final validation, publication, and checkpoints.

**Goal:** Ship strict OMP loop budgets, retained scripted conversations, and private immutable captures through Yacht-generated Harbor execution.

**Architecture:** Add task-owned `[execution]` declarations, separate from existing cold `[episodes]`. A launcher-owned controller keeps the schedule and captures outside all task mounts and drives a pinned OMP SDK process through duplex Docker exec stdio. OMP's awaited `session.agent.addBeforeModelCall` gate controls admission and records effective provider-visible context; ordinary native OMP tools and configured treatment riggings remain the evaluated harness.

**Tech Stack:** Python 3.12, Bun >=1.3.14, OMP 18.1.17, Harbor 0.20.0, rootless Docker.

**Spec:** `../yacht-evals/docs/yacht-runtime-eval-handoff.md`

The sibling consumer handoff supplies A-D requirements. This plan records the generic implementation contract; task content and scoring remain in yacht-evals.

**Source:** plane:YACHT-26

Consumers: YACHT-21 through YACHT-24.

## Global Constraints

- Preserve existing cold episodes and uncapped single-shot behavior. Never turn cold episodes into retained sessions.
- Never invent an OMP turn-cap CLI flag. Install the native awaited before-model gate before prompting.
- A loop is one admitted agent-core model invocation and its resulting tool batch. Multiple tools in a response consume one loop. Agent-core resamples/recovery calls each consume another admission. Provider-internal HTTP retries are not additional agent loops and must remain separately identified/unknown; do not claim request-count parity.
- No future script, capture bytes, hidden task truth, or controller event journal enters the task container. Only the currently delivered user message crosses stdin. Trial-private evidence is under `trial_dir/yacht-execution`, a sibling of mounted agent/verifier/artifacts directories.
- Capture raw bytes, status, digest and size. Missing differs from read failure; empty/malformed are successful bytes interpreted by the verifier.
- SDK session history stays in memory, with compaction, truncating transforms, automatic model fallback, title generation, memory, advisors and autonomous continuation disabled for controlled execution. Record enforced settings. Preserve ordinary rigging-supplied skills/context and model configuration; reject incompatible automation instead of silently measuring it.
- After the stock upstream prompt settles (SDK idle/abort; a frame field named quiescence means that SDK settle only), collect declared bounded point-in-time bytes, then deliver the next follow-up. There is no global workspace-quiescence guarantee and no OS cleanup between messages. Native background mutations after settle are observable agent/harness behavior, never runtime infrastructure. A task verifier may fail the task if it requested no-background behavior; that is task failure, not infrastructure. Keep the model-admission cap strict. Timeout uses cooperative abort. SDK idle or abort failure remains infrastructure, not a cold restart or a successful timeout. After the driver closes, final driver/container teardown still runs before verifier handoff; that termination does not change tool semantics during eval and does not freeze the workspace.
- Mandatory capture and transcript/context evidence ship; optional workspace before/after diffs and advisory judge are deferred explicitly.
- No provider/gateway changes, credential copying, benchmark runs, new TOML imports, or Pi episode implementation.
- Approved smoke budget (do not reuse a prior budget): Grok 4.6 medium, sequential, <=4 infrastructure trials, <=20 admitted loops aggregate, <=900 seconds aggregate inference wall, stop on infrastructure failure, no judge or paid-provider fallback.
- Operator-authorized local rootless build; pin a locally available digest (none recorded yet). No registry required. Public branch `omp-eval-runtime` requires operator publication approval immediately before push/PR.

## Chosen public contract

Task TOML for a bounded single shot:

```toml
[execution]
mode = "single"
max_turns = 30
message_timeout_seconds = 900
timeout_seconds = 900
```

Retained task TOML (initial message always `instruction.md`):

```toml
[execution]
mode = "retained"
max_turns = 30
message_timeout_seconds = 600
timeout_seconds = 7200
initial_turn_id = "initial"

[[execution.turns]]
id = "Q"
instruction = "The next scripted user message."

[[execution.captures]]
after = "Q"
path = "plans/retention-answers.json"
max_bytes = 1048576
```

All integers positive, booleans rejected. IDs match `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`, unique including initial. Paths are relative POSIX paths without dot/parent/empty components, absolute paths or backslashes. Capture IDs derive from stable turn ID + declaration index; duplicate (after,path) rejected. Capture max <=16 MiB; total bounded <=64 MiB per trial. Unknown keys rejected. Explicit `[execution]` and `[episodes]` conflict. New execution modes only OMP 18.1.17 on Harbor Docker/Linux; unsupported combinations fail during full render. Existing cold episodes with OMP max_turns use the same controller with a fresh process/session per episode; OMP caps require the pinned version. Other harness single-shot caps remain explicitly unsupported, not silently ignored.

The rendered job uses `agent.execution: {task_id: plan}` (same shape as task declaration, resolved strings). Harbor kwargs carry `execution` only in launcher config. Public regatta schema remains unchanged because declarations live in task.toml; publish task declaration schema separately if needed and synchronize Python job/launcher validation. The controller validates again before any process/inference.

## Internal interfaces

- Host `render_execution_plan(task_dir: Path) -> dict | None` and `validate_execution_plan(plan: object) -> None` normalize/validate task declarations; launcher uses the same packaged pure implementation or deliberately shared source, not divergent handwritten contracts.
- Controller `run_controlled_omp(*, environment, logs_dir: Path, instruction: str, model: str, plan: dict, env: dict | None = None) -> dict` runs single/retained plan and returns an execution summary with usage/cost. Its wrapper integrates cold capped episodes without altering uncapped legacy execution.
- Driver `omp_control.ts`, packaged with launcher and installed beside the task's OMP npm package. Newline JSON stdin commands `init`, `prompt`, `abort`, `state`, `shutdown`, each with `id`; stdout frames `ready`, `event`, `context`, `response`, `message_end` (controller lifecycle distinct from wrapped native event). Correlate IDs. A prompt response is emitted only after native SDK prompt settle, containing `ended`, `loops_started`, `loops_completed`, `continuation_possible`, timestamps, usage/cost and session ID. No overlap/queued follow-ups. Init takes model, overall deadline, enforcement policy only; never future turns.
- Driver gate remains closed between messages and at final stop; increments admission before stream scheduling and emits effective context for each admitted call. Natural text on last permitted call remains natural; denied next call after tool work is cap. Deadline yields timeout via cooperative abort. Preserve native raw events separately from controller records; do not count synthetic gate-stop messages as provider usage or loops.
- Evidence summary `schema: yacht.execution.v1`, `mode`, declared limits, session IDs, ordered `messages` (stable id, timings, ending, counts, continuation), `captures` (after, path, status missing/captured/error, bytes/sha256/artifact when captured), `valid`, error details, resolved model/harness/settings, usage/cost. Store `summary.json`, `events.jsonl`, per-message effective context and assistant replies in private execution dir. Propagate summary/references through Harbor trial -> machine_evidence.execution, with synchronized schema validation. Capture failure marks infrastructure invalid; missing does not.

### Task 1: Validate and render execution contracts

**Files:** new `src/yacht/courses/execution.py`; existing courses episodes/job/harness, contracts schemas, task-attempt JSON schema, attempts_from_trials; focused tests; reference docs.

**Produces:** normalized task plans and job `agent.execution`, launcher kwargs, `machine_evidence.execution` propagation. Own host-side files only; do not modify launcher agent/controller files.

- [ ] Write focused tests for real full rendering: single cap without episodes, retained stable IDs/captures, unknown/invalid/conflicting declarations, old OMP and unsupported harness rejection, uncapped legacy preservation, execution evidence round-trip. Main runs red before implementation.
- [ ] Implement additive parser and synchronized validators; install shared pure plan validation into launcher packaging through an agreed source file rather than two conventions.
- [ ] Keep OMP cold caps version-aware, leave Claude/declaration/native-cap behavior intact. Preserve max=1 legacy semantics unless execution declaration explicitly supplies cap.
- [ ] Publish exact declaration/examples and budget unit, unsupported combinations and evidence references. Do not include private eval truth/provider setup in public docs.
- [ ] Main runs focused tests and reviews this slice before publication.

### Task 2: Enforce budgets in the pinned OMP process

**Files:** new launcher `omp_control.ts` and focused Bun integration tests/helpers. Own JS driver and its tests only.

**Consumes:** stdin protocol above. **Produces:** strict bounded OMP SDK execution, preserved session history, full effective context/raw events, recoverability evidence.

- [ ] Write a deterministic test against real pinned OMP agent-core with injected stream provider: cap1/cap2, final text, multiple tools, looping tools, retry/admission distinctions, hanging cooperative tool and abort/continuation, no next-call admission at deadline. Main runs red before implementation.
- [ ] Use SDK createAgentSession with in-memory SessionManager; attach addBeforeModelCall before any prompt, never replace existing SDK stream wrappers. Preserve explicit model/config and ordinary treatment skills.
- [ ] Disable/validate implicit inference and history-rewriting settings; capture effective context, detect non-prefix history loss/compaction and invalidate rather than silently continuing.
- [ ] Implement correlated commands, no pending prompt overlap, awaited SDK abort/idle (failures remain infrastructure), no OS cleanup between messages, gate closed during capture/after final message. Final cleanup runs after the driver has closed, before verifier handoff.
- [ ] Emit complete lifecycle/evidence without secrets or hidden reasoning requirements; preserve user-facing text/fences and raw tool events.
- [ ] Main runs real SDK deterministic tests and approves driver behavior before live smoke.

### Task 3: Drive private Harbor conversations and checkpoints

**Files:** new launcher `controlled_omp.py`, bounded capture helper, duplex Docker transport; existing launcher agents/rigging and Dockerfile packaging; launcher-focused tests and smoke fixture/script.

**Consumes:** validated plan, driver protocol. **Produces:** real Harbor controlled single/retained/cold-capped execution and immutable controller-only evidence.

- [ ] Write deterministic lifecycle/capture tests: missing/empty/malformed/overwrite/read failure, traversal/symlink/size rejection, strict message sequencing, timeout cooperative-abort/SDK idle-abort failure, whole deadline stop, future script absent from task-facing payloads. Do not grade late native background mutation as infrastructure. A task verifier may fail the task if it requested no-background behavior; that is task failure, not runtime infrastructure. Main runs red before implementation.
- [ ] Pin Harbor 0.20.0 Docker/Linux duplex transport to its actual compose project/files/env/user/workdir semantics; no guessed container names. Start OMP through launcher-owned pipes, keep schedule/captures outside mounted task logs and exclude helper subprocesses from agent descendants.
- [ ] Integrate controlled OMP paths; each cold episode uses a new session while retained messages reuse one. Keep cold verifier early-stop; never use it for retained script.
- [ ] Capture allowlisted paths safely with bounded no-follow reads and independent immutable host writes after native prompt settle; captured bytes are point-in-time copies, not an atomic workspace snapshot under concurrent writes. Private artifacts become available only to trusted verification after agent execution, never by putting hidden truth in agent-readable logs.
- [ ] Preserve usage/context/budget summary on partial failure; infrastructure invalidity cannot silently appear as zero or successful retention.
- [ ] Package new helpers for an operator-authorized local rootless launcher build and a locally available digest (none recorded yet; no registry required); implement bounded unscored native Harbor smoke for actual cap, retention, capture, and leakage evidence. Run only under the approved smoke budget above.
- [ ] Main runs final suite/lint, reviews whole branch, documents precise smoke evidence and image digest, prepares governed PR, closes satisfied execution tracking, commits coherent result and runs standalone agent-checkpoint push.

## Verification and handoff

Baseline `direnv exec . uv run --frozen --no-sync -m unittest discover -s tests`: 1130 tests passed. New tests must assert observable behavior, not source strings. Main runs all validation centrally after parallel edits settle. Before publishing, require deterministic admission proof, full rendered supported/unsupported jobs, actual built launcher installation, bounded Grok tool/retention/capture evidence and private-mount audit. Operator-authorized local rootless build with a locally available digest (none recorded yet; no registry required) is required for image/live acceptance, not for reachable implementation. No success claim for unexercised surfaces.
