# Roadmap

This roadmap is organized around making YACHT useful as an open-source tool for
reproducible coding-agent evaluation.

The project north star is a general testbed for evaluating coding-agent setups
against controlled baselines across public benchmarks and custom evals. Work
that expands harnesses, rigging, runtime trust, course selection, and evaluator
adapters should take priority over polishing a single Pi+fff smoke path.

The most recently completed plan is
[Yacht 0.12: Durable Logbooks](0.12-durable-logbooks.md). It makes the
Logbook the authoritative, portable run-state interface before Yacht broadens
its harness or Course surface again.

The OMP and Codex expansion shipped in 0.11.0. The remaining sections below
are the longer-term product map; completed implementation notes are retained in
[Next phase opportunities](next-phase-opportunities.md) and
[Audit follow-ups](audit-followups.md).

## 1. Generalized Benchmark Surface

Goal: YACHT can run more than one hardcoded SWE-bench Lite smoke task and can
express benchmark subsets clearly.

Completed foundation:

- Select SWE-bench instances explicitly, from reusable task-set files, or with
  an ordered `max_instances` cap.
- Preserve selected tasks in plans, handoffs, runbooks, Scorecards, and reports.
- Keep native SWE-bench Docker grading as the source of benchmark truth.

Remaining:

- Add named sampling presets or randomized selection only with explicit,
  reproducible seed semantics.

## 2. Harness Generalization

Goal: Pi is one harness implementation, not the implicit model for the project.

Completed foundation:

- Make harness kind explicit and route prompt preflight, task attempts,
  provenance, and native evidence through adapter contracts.
- Ship Pi, Claude Code, OMP, Codex, declared, and local-smoke harnesses without
  changing the common task-attempt and reporting contracts.

Remaining:

- Add another first-class harness only when a concrete evaluation needs it.

## 3. Recipes and Rigging

Goal: arbitrary tools and setup changes can be tested as named, reusable
configuration.

Completed foundation:

- Model named setup, environment, prompt, tool, cache, config-file, skill, and
  MCP changes with capability checks before execution.
- Record Rigging and resolved tool provenance in task artifacts and reports.
- Keep local organization-specific recipes and secret coordinates outside the
  public examples.

Remaining:

- Add a new Rigging method only when an evaluation requires semantics the
  existing methods cannot express.

## 4. More Benchmark and Evaluator Adapters

Goal: YACHT can compare coding setups across more than one benchmark shape.

Completed foundation:

- Ship Course and evaluator seams exercised by SWE-bench, Terminal-Bench,
  LiveCodeBench, custom evals, and repository-local smoke workflows.
- Keep native harnesses responsible for execution and grading while Yacht owns
  normalized handoffs, evidence, and Scorecards.
- Separate evaluator adapters from Course loading and agent task context.

Remaining:

- Harden maintained adapters as their upstream contracts change.
- Add Aider Polyglot or advisory evaluators only as harness-agnostic Courses
  with a concrete consumer and evidence contract.

## 5. Runtime Trust and Preflight Evidence

Goal: valid observations depend on isolated, reproducible, machine-verified
agent runtimes.

Completed foundation:

- Keep container runtimes as the trusted path and host Nix as a development
  backend.
- Gate execution on runtime, harness, Rigging, tool, path-isolation, secret, and
  agent-prompt evidence before spending task tokens.
- Keep benchmark task containers and grading owned by native harnesses.

Remaining:

- Define trust and provenance requirements before adding remote workers.

## 6. Repeated Runs and Result Quality

Goal: YACHT can support publication-quality or database-quality comparisons.

Completed foundation:

- Model benchmark repetitions explicitly as a parent Logbook with indexed
  child Logbooks.
- Preserve per-run Scorecards and produce aggregate JSON and Markdown reports.

Remaining:

- Extend aggregate reporting with cross-run cost and tool-use distributions.
- Add controls for task sampling and randomization.
- Keep LLM outcomes labeled as observations, not deterministic cached facts.

## 7. Logbook as Durable Artifact

Goal: a logbook should be useful to a human, a CLI, and external analysis
tools.

Completed in 0.12:

- Add a portable, versioned run index with lifecycle state, identity,
  comparisons, artifacts, timestamps, generated reports, and child Logbooks.
- Make the shared Logbook reader authoritative for status, report, latest-run
  selection, and dashboard discovery while preserving historical Logbooks.
- Keep JSON status output and durable Markdown and HTML report output available
  through the public commands.

Remaining:

- Expand report navigation to every transcript, candidate patch, native report,
  grading report, and failed gate recorded by the Logbook.

## 8. First-Run UX

Goal: a new user can run a credible benchmark smoke without knowing YACHT's
internal command graph.

Completed foundation:

- Ship `yacht doctor`, supported smoke examples, full-run commands, generated
  runbooks, actionable next commands, and Logbook-contained native artifacts.
- Keep token-free local smoke paths available for contributor and release
  checks.

Remaining:

- Shorten first-run documentation as packaging and supported adapter setup
  stabilize.

## 9. Ecosystem Readiness

Goal: public artifacts and local workflows are stable enough for other tools
and scripts to consume.

Near-term slices:

- Keep schema versions explicit and language-neutral.
- Ensure all public reports have machine-readable equivalents.
- Avoid hardcoding local password-manager or user-environment assumptions.
- Make secrets explicit references, not copied state.
- Keep runtime backends abstract enough for remote workers and reproducible
  container execution.
- Treat shared evals as signed or provenance-rich logbooks.
