# Audit-Backed Plan

This plan distills the project audit into the implementation order YACHT should
carry forward. The raw audit is not part of the project record; this document
keeps the decisions and sequencing that matter.

## Product Priority

The primary 0.1 success case is:

> A new user can run a small credible benchmark locally, inspect the logbook,
> and understand whether the result is trustworthy.

That does not make adapter extensibility optional. The local benchmark path
should be improved in a way that also lowers the cost of adding the next course
or evaluator adapter.

## Agreed Order

1. Finish critical quick wins.
2. Add safety nets before broad refactors.
3. Move contracts toward schema-first validation.
4. Dedupe course/evaluator adapter mechanics.
5. Consolidate smoke workflows around configured harnesses.
6. Extract larger workflow pipelines after trust-boundary tests exist.

## Critical Quick Wins

These are small, reviewable changes that reduce obvious user or maintainer
friction.

- Document first-run prerequisites: Python 3.12, `uv`, Git, Docker, the
  repo-local runtime image, provider secrets, and the native SWE-bench harness.
- Validate artifact-path names from config, including task IDs, vessel names,
  and comparison names, before they are interpolated into logbook paths.
- Replace production `assert` checks used for input validation with explicit
  project errors.
- Cache SWE-bench dataset records per process so multi-task and multi-vessel
  runs do not repeatedly reload and scan the same split.

## Safety Nets

Add machinery that preserves current discipline as the project becomes easier
for outside contributors to run and modify.

- Add ruff lint and format checks to CI.
- Add coverage reporting to CI without an initial threshold.
- Add direct tests for the trust-boundary modules:
  - `yacht.config.loader`
  - `yacht.preflight.execution`
  - `yacht.runtimes.container`
- Add CLI dispatch coverage for every command before restructuring `cli.py`.
- Add type checking later, after artifact-boundary code is less noisy.

## Contract Direction

ADR 0005 records the contract decision:

- JSON Schema files under `schemas/` are the primary structural contract.
- Python validators remain the call-site interface.
- Python validation should focus on schema loading, semantic checks, dynamic
  adapter/capability checks, and error normalization.
- `yacht.contracts` should not import from higher-level implementation modules
  such as `yacht.courses` or `yacht.runtimes`.

The goal is not to split the large handwritten validator into smaller
handwritten validators. The goal is to shrink handwritten structural validation
over time while preserving current caller ergonomics.

## Architecture Work

Once the quick wins and safety nets are in place, prioritize architecture work
that improves both local-user credibility and future adapter additions.

- Create shared course/evaluator grading and prediction helpers for SWE-bench
  and custom eval before adding Terminal-Bench.
- Consolidate repeated JSON file loading/writing behind one logbook-facing
  module with consistent missing-file and invalid-artifact errors.
- Move smoke workflows onto configured harnesses so Pi remains one adapter, not
  an implicit workflow assumption.
- Expand the logbook run index into the default run-state interface for status
  and report workflows.
- Extract the `real_benchmark_eval` pipeline only after direct tests cover
  preflight execution and container runtime behavior.

## Deferred

These are useful but should not block the first credible local-user path.

- Plugin or entry-point adapter discovery.
- Parallel task execution.
- A full `jsonschema` migration across every artifact family in one change.
- A broad CLI module split before command dispatch tests exist.
- Strict coverage thresholds before the trust-boundary tests land.
