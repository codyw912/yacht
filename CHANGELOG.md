# Changelog

## Unreleased

- Added `benchmark-aggregate` for summarizing resolution and usage across
  multiple completed benchmark logbooks.
- Added `real-benchmark-repetitions` to run repeated real benchmark evals into
  child logbooks and persist an aggregate summary.
- Added `benchmark-status` and `benchmark-report` support for repeated-run parent
  logbooks.
- Fixed agent-prompt preflight JSON extraction when agents wrap the required
  JSON object in a Markdown fence with surrounding text.
- Added stderr progress updates for long-running real benchmark commands while
  preserving final JSON on stdout.
- Added per-run rows to benchmark aggregate reports so repeated benchmark runs
  expose individual run usage, outcomes, and child logbook paths.
- Added automatic `benchmark-report.md` generation for repeated benchmark parent
  logbooks when at least one child run completes.
- Added timestamped default logbooks for `real-benchmark-repetitions` when
  `--logbook` is omitted.
- Compacted `real-benchmark-repetitions` output by replacing the embedded full
  aggregate with a smaller aggregate summary and artifact paths.
- Added repeated-run aggregate statistics for resolution rate, tokens, cost,
  duration, and tool calls by vessel and comparison delta.
- Added explicit agent/tool/benchmark surface metadata to provisioning configs,
  runtime plans, runtime instance dry-runs, and real benchmark runbooks.
- Added typed rigging install steps so tool setup can describe agent extensions,
  MCP servers, packages, binaries, container images, preinstalled tools, or
  custom commands without treating npm as the generic install model.
- Real benchmark commands now select the agent harness from configured runtime
  surface metadata instead of assuming Pi at the orchestration boundary.
- Real benchmark artifacts, status output, and scorecard reports now surface the
  configured agent, tool, and benchmark harness metadata used for the run.
- Runtime plans and dry-run instances now report whether typed rigging install
  steps are supported by the selected runtime backend before setup commands run.

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
