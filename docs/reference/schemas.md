# Schema Contract

YACHT keeps its durable cross-language contract in JSON Schema files under
`schemas/`. Python is the current control-plane implementation, but persisted
artifacts should remain consumable by other tools, hosted services, and future
runners.

## Core Artifacts

- `yacht.regatta.v1.schema.json` for regatta configuration.
- `yacht.wake.v1.schema.json` for deterministic mock-run wake artifacts.
- `yacht.scorecard.v1.schema.json` for deterministic mock-run scorecards.
- `yacht.runtime-instances.v1.schema.json` for redacted runtime snapshots.

## Preflight Artifacts

- `yacht.preflight.v1.schema.json` for per-vessel runtime and rigging evidence.
- `yacht.preflight-summary.v1.schema.json` for preflight command summaries.
- `yacht.preflight-evidence-report.v1.schema.json` for benchmark eligibility
  audits.

## Task Attempt Artifacts

- `yacht.task-attempt.v1.schema.json` for per-agent task attempt evidence.
- `yacht.task-attempt-scorecard.v1.schema.json` for task attempt summaries,
  including token, cost, duration, and tool-call rollups.
- `yacht.smoke-readiness-report.v1.schema.json` for real smoke-run readiness
  checks.
- `yacht.real-smoke-runbook.v1.schema.json` for shareable real smoke runbooks.

## Benchmark Artifacts

- `yacht.course-handoff.v1.schema.json` for native benchmark handoff plans.
- `yacht.swe-bench-grading.v1.schema.json` for normalized SWE-bench grading
  reports.
- `yacht.benchmark-execution-plan.v1.schema.json` for benchmark readiness plans.
- `yacht.benchmark-readiness-summary.v1.schema.json` for compact launch-gate
  summaries.
- `yacht.benchmark-launcher-handoff.v1.schema.json` for native launcher
  commands.
- `yacht.benchmark-launch-result.v1.schema.json` for native launcher execution
  results.
- `yacht.benchmark-scorecard.v1.schema.json` for benchmark comparison
  scorecards.

## Configuration Sections

Regatta configs may include:

- `secrets` for explicit env/file secret references without values.
- `runtimes` for agent runtime recipes such as `container` or `host-nix`.
- `riggings` for named setup, environment, prompt, tool, or cache changes.
- `course.adapter` for native benchmark harnesses such as SWE-bench.
- `preflight` for regatta-level failure policy.
- `comparisons` for groups of vessels interpreted together.

The default preflight failure policy is `abort-group`: if any required
preflight check fails for a vessel in a comparison, YACHT skips task execution
for that comparison group rather than spending tokens on an invalid paired
result.

