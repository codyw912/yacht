# Changelog

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
