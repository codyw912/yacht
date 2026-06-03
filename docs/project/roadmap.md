# Roadmap

This roadmap is organized around making YACHT useful as an open-source tool for
reproducible coding-agent evaluation.

The project north star is a general testbed for evaluating coding-agent setups
against controlled baselines across public benchmarks and custom evals. Work
that expands harnesses, rigging, runtime trust, course selection, and evaluator
adapters should take priority over polishing a single Pi+fff smoke path.

For the current audit-backed implementation backlog, see
[Next phase opportunities](next-phase-opportunities.md).

## 1. Generalized Benchmark Surface

Goal: YACHT can run more than one hardcoded SWE-bench Lite smoke task and can
express benchmark subsets clearly.

Near-term slices:

- Generalize SWE-bench task selection with explicit `instance_ids`.
- Add bounded task controls such as `max_tasks` or named smoke presets.
- Keep task selection visible in handoff, runbook, scorecard, and reports.
- Add examples for one-task, small multi-task, and user-selected task sets.
- Preserve native SWE-bench Docker grading as the source of benchmark truth.

## 2. Harness Generalization

Goal: Pi is one harness implementation, not the implicit model for the project.

Near-term slices:

- Make harness kind explicit in config and runtime surfaces.
- Define a harness adapter contract for prompt preflight and task attempts.
- Keep task-attempt artifacts comparable across harnesses.
- Add a second harness adapter, chosen for reliability and low integration
  complexity.
- Ensure reports show which harness ran each vessel.

## 3. Recipes and Rigging

Goal: arbitrary tools and setup changes can be tested as named, reusable
configuration.

Near-term slices:

- Make rigging recipes more explicit about install steps, env, prompts,
  expected tools, state paths, and cache policy.
- Model install/config capabilities such as CLI command, MCP server, skill,
  prompt pack, config file, env var, setup command, and agent extension.
- Add reusable example recipes for fff, MCP-style tools, CLI tools, and
  prompt-only variants.
- Record rigging provenance in reports so users can see what changed between
  vessels.
- Add stricter preflight smoke contracts for tool availability and
  configuration.
- Preserve a path for local recipes that depend on organization-specific tools
  or secrets without committing those details to public examples.

## 4. More Benchmark and Evaluator Adapters

Goal: YACHT can compare coding setups across more than one benchmark shape.

Near-term slices:

- Harden SWE-bench Lite into a documented supported adapter.
- Add multi-task SWE-bench smoke support with clearer sampling controls.
- Add Terminal-Bench as the first post-SWE-bench adapter target.
- Add LiveCodeBench Lite as a recognizable model/code benchmark target.
- Add a tiny repo-local benchmark adapter for fast CI and docs examples.
- Define an evaluator adapter interface separate from native benchmark
  launchers.
- Defer Aider Polyglot unless it can be used as a harness-agnostic
  course/evaluator rather than an Aider harness integration.
- Defer LLM/code-quality evaluators until the benchmark path is stable, but
  keep report and artifact shapes open to advisory evaluators.

## 5. Runtime Trust and Preflight Evidence

Goal: valid observations depend on isolated, reproducible, machine-verified
agent runtimes.

Near-term slices:

- Keep containerized agent runtimes as the trusted execution path.
- Preserve host-nix as a development backend, not the basis for strong eval
  claims.
- Add preflight checks for harness availability, tool installation, MCP
  reachability, prompt/skill configuration, isolated paths, and secret
  injection.
- Make unsupported rigging capabilities fail before task tokens are spent.
- Keep benchmark task containers and benchmark grading owned by native harnesses
  when those harnesses exist.

## 6. Repeated Runs and Result Quality

Goal: YACHT can support publication-quality or database-quality comparisons.

Near-term slices:

- Model trials/repetitions explicitly.
- Report variance, pass rates, failure rates, cost distributions, and tool-use
  distributions across repeated runs.
- Preserve per-trial logbooks while producing aggregate scorecards.
- Add controls for task sampling and randomization.
- Make it clear that LLM outcomes are observations, not deterministic cached
  facts.

## 7. Logbook as Durable Artifact

Goal: a logbook should be useful to a human, a CLI, and external analysis
tools.

Near-term slices:

- Add a run index artifact that lists status, config, comparisons, vessels,
  artifact paths, timestamps, and final report paths.
- Add a single `yacht report --logbook` entry point that detects smoke vs
  benchmark logbooks.
- Expand reports with links/paths to transcripts, candidate patches, native
  reports, grading reports, and failed gates.
- Add durable Markdown report output for benchmark runs by default or as a
  documented release checklist step.
- Add compact JSON summary output for automation and analysis.

## 8. First-Run UX

Goal: a new user can run a credible benchmark smoke without knowing YACHT's
internal command graph.

Near-term slices:

- Add `yacht doctor` for host prerequisites: Docker, runtime image,
  configured secrets, native SWE-bench harness, writable logbook paths, and
  basic network access.
- Add a focused first benchmark runbook for supported examples.
- Clean generated native harness files from the repo root by default and guide
  users toward logbook-contained artifacts.
- Improve error messages so they name the next command to run or artifact to
  inspect.

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
