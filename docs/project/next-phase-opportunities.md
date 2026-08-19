# Next Phase Opportunities

Status: background architecture backlog. The active short-term plan is
[Yacht 0.12: Durable Logbooks](0.12-durable-logbooks.md); entries below retain
the state in which they were originally evaluated and may already be shipped.

This note tracks the audit findings after the codebase architecture cleanup.
The shared direction is to broaden what YACHT can credibly evaluate, rather
than keep polishing the first Pi+fff/SWE-bench proof path.

The opportunities below are all worth doing. The recommended order is based on
which work most directly reduces hardcoded assumptions about Pi, fff,
SWE-bench Lite, and the current command graph.

## Recommended Order

1. Make smoke workflows harness-configured.
2. Deepen rigging execution behind runtime capabilities.
3. Split course adapters from evaluator adapters.
4. Make the logbook the run-state interface.
5. Consolidate schema validation around the public schema files.

## 1. Harness-Configured Smoke Workflows

Current state:

- Real benchmark eval selects the configured harness from runtime surface
  metadata.
- Real smoke eval and real smoke runbook select the configured harness from the
  regatta.
- The explicit `pi-smoke-eval` command remains Pi-specific.

Opportunity:

Move smoke workflows onto the same configured-harness path as real benchmark
eval. Pi should remain one adapter, not the implicit workflow architecture.

Likely first slice:

- Done: update `real-smoke-eval` and related runbook code to resolve the
  configured harness from the regatta.
- Done: add coverage proving the local-smoke example works without Pi through
  the generic real smoke path.
- Next: decide whether to keep `pi-smoke-eval` as a compatibility command,
  rename it as a focused adapter command, or remove it after downstream docs no
  longer need it.

Why it matters:

This directly supports adding another real harness adapter and keeps task
attempt artifacts comparable across harnesses.

## 2. Rigging Execution and Runtime Capabilities

Current state:

- Rigging config can describe typed install steps.
- Runtime rigging setup planning and execution live in `yacht.runtimes`
  instead of being embedded directly in backend preparation.
- Runtime execution supports `preinstalled`, `agent-extension`, and
  `custom-command`.
- Unsupported capabilities are correctly blocked before task tokens are spent.

Opportunity:

Create a deeper rigging setup module that turns typed install steps into
runtime-specific executable or preflight-only plans.

Likely first slice:

- Done: move rigging install planning out of runtime backend preparation.
- Done: execute `custom-command` install steps through the runtime command
  prefix.
- Next: model remaining methods explicitly: CLI command, MCP server, skill,
  prompt pack, config file, env var, setup command, package, binary, and
  container image.
- Keep unsupported methods visible in dry-run and preflight evidence.

Why it matters:

YACHT's config already promises richer rigging than it can execute. This makes
tools, prompts, skills, MCP servers, and setup commands first-class surfaces
for comparison.

## 3. Course and Evaluator Adapter Split

Current state:

- Course and evaluator adapter interfaces are split in `yacht.courses.registry`.
- The legacy `benchmark_adapter()` facade remains for compatibility while
  workflows move onto the narrower course/evaluator interfaces.
- SWE-bench and custom eval both fit through this shape, but custom eval is not
  truly a native benchmark harness in the same sense as SWE-bench.
- Terminal-Bench is the preferred next adapter target, followed by
  LiveCodeBench Lite. Aider Polyglot is deferred unless it can be used as a
  harness-agnostic course/evaluator.

Opportunity:

Split adapter responsibilities so courses, candidate extraction, native
launching, grading, and evaluator normalization can evolve independently.

Likely first slice:

- Done: define the smallest course interface needed by task attempts: prompt
  instructions, task context, and workspace materialization.
- Done: define a separate evaluator interface for converting produced attempts
  into normalized grading observations.
- Done: keep SWE-bench native launch/grading as one evaluator implementation.
- Next: add a Terminal-Bench adapter spike using the split interfaces.

Why it matters:

This makes Terminal-Bench, LiveCodeBench Lite, tiny repo-local evals, advisory
evaluators, human-review evaluators, and other benchmark families easier to add
without forcing everything into a SWE-bench-shaped module.

## 4. Logbook Run-State Interface

Current state:

- Real benchmark and real smoke workflows write a `run-index.json` artifact
  owned by `yacht.logbook`.
- `benchmark-status` prefers `run-index.json` when it is present and preserves
  artifact probing for older logbooks.
- The roadmap calls for a run index that lists status, config, comparisons,
  vessels, artifact paths, timestamps, and final report paths.

Opportunity:

Make `yacht.logbook` own a run index artifact and the interface for reading
run state.

Likely first slice:

- Done: add a run index artifact written by real benchmark and smoke workflows.
- Done: teach `benchmark-status` to prefer the index when present while
  preserving existing artifact detection.
- Next: expand the index into the default interface for status/report
  workflows, including final report paths and smoke-vs-benchmark detection.

Why it matters:

This improves locality for status/report behavior and makes logbooks easier for
external tools to index, compare, publish, or sign later.

## 5. Schema Validation Consolidation

Current state:

- Public schema files live under `src/yacht/schemas/`.
- A large handwritten Python validator in `yacht.contracts` mirrors much of
  that contract.

Opportunity:

Make the public schema files the primary structural contract and keep Python
validation focused on semantic checks that JSON Schema cannot express cleanly.

Likely first slice:

- Inventory artifact schemas already represented in `src/yacht/schemas/` but
  still validated only or mostly by handwritten Python.
- Introduce schema-file loading for one low-risk artifact family.
- Preserve current `ConfigError` and `SchemaValidationError` ergonomics for
  callers.

Why it matters:

YACHT's durable contract is language-neutral. Reducing drift between schema
files and Python validators improves ecosystem readiness and lowers the cost of
adding new artifacts.
