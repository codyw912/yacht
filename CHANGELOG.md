# Changelog

## 0.5.0 - Statistical Verdicts, LiveCodeBench, and Aider Polyglot

YACHT 0.5.0 makes comparison verdicts statistically honest, adds two
benchmark courses — LiveCodeBench through its official evaluator and
Aider Polyglot on the Harbor foundation — and publishes the contract for
contributing new courses.

### Statistical rigor (ADR 0013)

- Comparison scorecards now carry a `statistics` block per comparison:
  Wilson score intervals on resolution rates and an exact paired sign
  test over discordant tasks, all stdlib-only.
- Resolution verdicts are graded by evidence: `insufficient-evidence`
  (fewer discordant tasks than the significance threshold — an
  observation, not a conclusion), `not-distinguishable` (p >= 0.05), or
  `evidence-of-difference` (p < 0.05). Reports append the grade to the
  decision line instead of presenting raw deltas as findings.
- Repetition aggregates replace the old variance heuristics with
  t-based 95% confidence intervals on per-run deltas, graded the same
  way; HTML reports badge the grade and label single runs as
  observation-only.

### LiveCodeBench course (ADR 0014)

- Added the `livecodebench` course: YACHT runs the rollout (competitive
  programming problems fetched with full context from the pinned
  dataset), and grading is delegated to the official LiveCodeBench
  evaluator, pinned by commit in a dedicated launcher image
  (`containers/lcb-runner`) so untrusted generated code executes only in
  a container.
- Course configs declare the contest-date window (`start_date` /
  `end_date`) that selects the problem set; unattempted window problems
  are padded into the evaluator input as required by the harness and
  reported distinctly from real submissions. The window is carried
  through every pipeline artifact and validated at each stage.
- Added `examples/container-claude-code-livecodebench-smoke.toml`
  (haiku vs sonnet on two problems) and a LiveCodeBench reference page.
  Validated live end to end with a real token-spending comparison run.

### Aider Polyglot course

- Registered `aider-polyglot` (225 Exercism tasks across six languages)
  on the Harbor course foundation from 0.4.0 — same yacht-owned agents,
  pinned launcher, rigging, and install-only preflight; only the
  dataset pin and grading schema differ. Added
  `examples/aider-polyglot-claude-code-versions-smoke.toml`.

### Project

- Documented the course contract (`docs/reference/adding-a-course.md`):
  the decision tree between yacht-run and native-rollout shapes, the
  adapter surfaces to implement, the normalized native report
  invariants, and the pinning and trust rules a new course must satisfy.
  CONTRIBUTING.md now leads with it.
- Course adapter blocks are rebuilt from one shared helper across all
  pipeline artifacts, fixing mid-run validation failures where
  LiveCodeBench window fields were dropped between stages.

## 0.4.0 - Terminal-Bench and the Harbor Course Foundation

YACHT 0.4.0 adds the second real benchmark course — Terminal-Bench 2.0 —
and, underneath it, a general foundation for running Harbor-format courses
with YACHT-owned agents in a hermetic launcher (ADR 0011, ADR 0012).

### Terminal-Bench course

- Added the `terminal-bench` course: rollout and verification are
  delegated to Terminal-Bench's official Harbor harness, which builds each
  task's own container, installs the pinned agent inside it, runs the
  agent, and runs the task's tests. Courses can now declare native
  rollout, and the pipeline skips YACHT-side task attempts for them.
- Harbor's per-trial results translate into the normalized grading
  reports the scorecard consumes (verifier reward to resolved/unresolved,
  exceptions to errors, missing trials to incomplete), and task-attempt
  artifacts are synthesized from trial evidence so Terminal-Bench runs
  carry the same usage and provenance surface as harness-run attempts —
  harness version and model resolved from what Harbor actually installed
  and ran, null when absent, never guessed.
- Added `examples/terminal-bench-claude-code-versions-smoke.toml`
  (pinned Claude Code 2.1.211 vs 2.1.215 on one task) and a
  Terminal-Bench reference page. Validated live end to end, including a
  real token-spending comparison run.

### Yacht-owned agents and the pinned launcher (ADR 0012)

- Vessels on Harbor courses run through YACHT's own agent classes, baked
  into a pinned launcher image (`containers/harbor-launcher`): the pinned
  harness is installed and YACHT's typed rigging steps are applied inside
  the task container — pinned npm `package` installs, `config-file`
  content behind a traversal guard, and stdio `mcp-server` entries.
  Unpinned packages and inexpressible methods are rejected before launch,
  and trial evidence names the agent implementation.
- The orchestrator is hermetic: Harbor and its dependencies resolve at
  image build time, and the launcher container sees only the mounted
  trial directory, the Docker socket for sibling task containers, and
  explicitly declared secret environment variables.
- Added the `harbor` runtime backend: recipes declare the launcher
  image, harness, and a required pinned `harness_version` — no
  ceremonial commands or flakes — and validation enforces course/backend
  agreement in both directions. No rigging ever executes on the host for
  these vessels.
- Added the `install-only` preflight check: Harbor's install-only trial
  mode proves agent-plus-rigging installation in a real task container
  before tokens are spent, passing only when the trial records the
  installed agent version.

### Project

- Course-agnostic grading, artifact, and attempt helpers extracted from
  the SWE-bench package into shared course modules.
- Recorded the Terminal-Bench decision (ADR 0011) and the Harbor-course
  architecture with its independence constraints (ADR 0012): YACHT
  schemas remain the contract, official native harnesses remain grading
  truth, and the roadmap keeps a maintained non-Harbor course.
- The dashboard skips unreadable directories during logbook discovery
  instead of failing the whole scan.

## 0.3.0 - Tool-Claim Validation, Provenance, and the Dashboard

YACHT 0.3.0 delivers the tool-claim validation workstream: a second real
harness, executable MCP-server rigging, human-friendly HTML verdicts, run
provenance for granular aggregation, and a local dashboard over logbooks.

### Claude Code harness

- Added the `claude-code` harness adapter alongside `pi` (ADR 0008): task
  attempts run headless `claude --print --output-format stream-json`, tool
  calls, tokens, cost, and duration are parsed from the stream into the same
  task-attempt fields Pi populates, and an exit-0 run without a valid result
  message fails loudly instead of recording estimated usage.
- Added the pinned `containers/claude-code-runtime` image
  (`@anthropic-ai/claude-code@2.1.211` on Node 22, isolated `yacht` user).
- Permission bypass (`--dangerously-skip-permissions`) is refused on
  non-container backends; agent-prompt preflight runs without it.

### Rigging for tools under test

- `config-file` installs write declared content into the trial home behind a
  traversal guard, and `package` installs execute pinned npm targets through
  the runtime, with every setup action recorded as evidence in task-attempt
  artifacts.
- `mcp-server` installs are executable through a harness adapter hook that
  renders declared servers into the harness's own config format inside the
  trial home (Claude Code: user-scope `mcpServers`); harnesses without a
  renderer still block the method before tokens are spent.
- Added `examples/container-claude-code-mcp-real-task-smoke.toml` (pinned
  tool version, offline MCP server start, live-tool preflight) and the
  "Validating a Tool Claim" tutorial documenting the full loop.
- Vessels whose runtime and riggings declare no preflight checks are
  rejected with an actionable error instead of passing an empty preflight.

### HTML reports

- `yacht report --format html` writes a single self-contained file (no
  scripts, no external assets) with a verdict banner, small-sample and
  run-variance badges, per-vessel outcomes and usage, tool-call evidence
  tables, and per-task results; repetition parent logbooks render the
  aggregate with variance-aware verdicts.

### Run provenance (ADR 0009)

- Every task attempt records a `provenance` block resolved only from
  evidence the run produces: harness name and version from the pinned image
  tag, configured versus API-reported model, runtime backend and image,
  pinned tool versions, and the yacht version. Unresolvable values are null,
  never guessed.
- Scorecards and benchmark aggregates collapse provenance upward; any
  dimension where runs disagree becomes null and is labeled under `mixed`,
  with a warning badge and provenance tables in aggregate reports, so
  blended results are never presented as homogeneous.

### Dashboard (ADR 0010)

- Added `yacht serve`, the seventh command: a stdlib-only, localhost,
  read-only dashboard that rescans a root of logbooks and renders from
  artifacts on every request. The index groups runs by regatta and course
  with broken logbooks shown visibly; per-run pages reuse the HTML report
  renderer verbatim.
- The `/vessels` view filters and groups every vessel run by hierarchical
  provenance facets through bookmarkable URL query parameters — a harness
  filter matches every version while `harness.version` matches exactly —
  with mixed-provenance records confined to a labeled unknown bucket.

## 0.2.0 - First Published Release

The first release distributed on PyPI as `yacht-eval` (the import package and
CLI stay `yacht`). YACHT 0.2.0 consolidates the command surface, hardens the
first-run path, and generalizes the evaluation pipeline that 0.1.0 proved.

### CLI

- Consolidated the user-facing CLI to six commands: `doctor`, `run`,
  `validate`, `status`, `report`, and the `internals` group holding the
  pipeline stage commands for debugging and incremental re-runs (ADR 0006).
- Added `yacht doctor` for host prerequisite checks: Python, uv, Git, the
  Docker CLI and daemon, logbook writability, the native SWE-bench harness,
  and config-aware runtime image and secret checks, each with an actionable
  hint.
- Unified `yacht run` to execute the full pipeline and detect smoke versus
  benchmark courses from the config, with `--repetitions` for repeated
  benchmark runs aggregated under one parent logbook.
- Unified `yacht status` and `yacht report` to detect the run type through
  the logbook run index and default to `./logbook`, then the most recent
  yacht logbook.
- Runbook artifacts are written automatically at the start of each run, and
  every next-step hint emitted into artifacts names a runnable command.

### Evaluation pipeline

- Required secrets are validated before task context loading and workspace
  materialization, so misconfigured runs fail before network work or tokens
  are spent.
- SWE-bench dataset records are cached per process, keyed by dataset and
  split, so multi-task and multi-vessel runs load each split once.
- Task IDs, vessel names, and comparison names from config are validated as
  path-safe before they are interpolated into logbook paths.
- Repeated benchmark runs produce per-run rows, aggregate statistics for
  resolution rate, tokens, cost, duration, and tool calls, and an automatic
  markdown report on the parent logbook.
- Typed rigging install steps describe agent extensions, MCP servers,
  packages, binaries, container images, preinstalled tools, and custom
  commands; unsupported capabilities are blocked with explicit
  `runtime-capability` preflight evidence before setup commands run.
- The agent harness is selected from configured runtime surface metadata
  instead of assuming Pi, and artifacts report which harness ran each vessel.
- Fixed agent-prompt preflight JSON extraction when agents wrap the required
  JSON object in a Markdown fence, and fixed smoke readiness resolution for
  relative logbook paths.

### Project

- The unit suite is hermetic (no network) and runs in seconds; CI enforces
  ruff lint and formatting and reports coverage.
- Production input validation uses explicit project errors instead of
  asserts.
- Recorded architecture decisions for the six-command CLI (ADR 0006) and the
  `yacht-eval` distribution name (ADR 0007).

## 0.1.0 - First Usable Benchmark Smoke

- Added a real end-to-end SWE-bench Lite smoke path for containerized Pi
  baseline vs containerized Pi+fff.
- Added runtime and rigging preflight evidence before task tokens are spent.
- Added SWE-bench task context loading, per-task repository checkout, agent
  task attempts, candidate patch extraction, native SWE-bench Docker grading,
  and normalized benchmark scorecards.
- Added a one-task smoke config and a two-task small smoke config:
  `examples/container-pi-fff-real-benchmark-smoke.toml` and
  `examples/container-pi-fff-real-benchmark-small.toml`.
- Added benchmark status and report output with notable deltas, per-vessel
  usage, per-task usage, per-task outcomes, and artifact paths.
- Added runbook generation for real benchmark runs so users can inspect the
  exact commands and expected artifacts before spending provider tokens.
