# Changelog

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
