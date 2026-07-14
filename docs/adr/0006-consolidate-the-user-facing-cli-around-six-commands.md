# ADR 0006: Consolidate the User-Facing CLI Around Six Commands

## Status

Accepted

## Context

The CLI grew one command per pipeline stage while the first real benchmark
path was being proven. It now exposes 33 subcommands from a single large
`cli.py`, and running the primary supported workflow requires knowing a
four-command sequence (`real-benchmark-runbook`, `real-benchmark-eval`,
`benchmark-status`, `benchmark-report`) plus the right example config and a
Docker image tag. Several commands overlap (`run`, `local-smoke-eval`,
`pi-smoke-eval`, `real-smoke-eval`), some are harness-specific in ways the
architecture no longer requires, and none of them checks host prerequisites
before spending time or tokens.

The 0.1 success case is that a new user can run a small credible benchmark
locally, inspect the logbook, and understand whether the result is
trustworthy. The current surface is the largest obstacle to that. There are
no external users yet, so renames and deletions are still cheap.

The staged pipeline itself is sound and well-tested. The problem is that the
stages are the front door, not that they exist.

## Decision

We will consolidate the user-facing CLI to six commands for 0.1:

- `yacht doctor` checks host prerequisites: Docker availability, the runtime
  image, configured secrets, the native SWE-bench harness, and writable
  logbook paths.
- `yacht validate <config>` keeps its current role.
- `yacht run <config>` executes the full pipeline (preflight, task attempts,
  grading, scorecard), detects smoke versus benchmark courses from the
  config, and accepts `--repetitions`.
- `yacht status [--logbook]` reads run state through the run index and
  defaults to the most recent logbook.
- `yacht report [--logbook]` detects the run type and keeps the existing
  `--vessel`, `--task`, `--format`, and `--output` filters.
- `yacht internals <stage>` namespaces the existing stage commands (handoff,
  benchmark-plan, launch, collect-grading, predictions, and peers) for
  debugging and incremental re-runs.

We will delete `pi-smoke-eval`, `local-smoke-eval`, `real-smoke-eval`,
`real-benchmark-eval`, `real-benchmark-runbook`, and `latest-logbook`. The
current `run` command's semantics are replaced by the new `yacht run`.

Sequencing follows the audit-backed plan: CLI dispatch coverage for every
existing command lands before `cli.py` is restructured, and the restructure
into command modules is behavior-preserving before any surface changes.

## Consequences

- A new user can go from clone to inspected scorecard knowing three commands
  (`doctor`, `run`, `report`), which is the 0.1 success case.
- Deleting and renaming commands now, before any release, avoids a
  compatibility burden that would otherwise be permanent.
- The staged pipeline remains fully scriptable under `yacht internals`, so
  debugging a failed run does not regress.
- Every example, doc, and CI invocation that names a removed command must be
  updated in the same change that removes it.
- `yacht run` takes on config-driven dispatch (smoke versus benchmark) that
  was previously the user's job; wrong detection is now a bug class, so the
  detection must be covered by dispatch tests.
- The `cli.py` split touches every command path and is only safe after the
  dispatch coverage exists; that ordering is a hard dependency.
