# Roadmap

This roadmap is organized around making YACHT useful as an open-source tool for
reproducible coding-agent evaluation.

## 1. First-Run UX

Goal: a new user can run a credible benchmark smoke without knowing YACHT's
internal command graph.

Near-term slices:

- Add `yacht doctor` for host prerequisites: Docker, runtime image,
  configured secrets, native SWE-bench harness, writable logbook paths, and
  basic network access.
- Add a focused first benchmark runbook for
  `examples/container-pi-fff-real-benchmark-smoke.toml`.
- Clean generated native harness files from the repo root by default and guide
  users toward logbook-contained artifacts.
- Improve error messages so they name the next command to run or artifact to
  inspect.

## 2. Logbook as Durable Artifact

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

## 3. Recipes and Rigging

Goal: arbitrary tools can be tested as named, reusable configuration.

Near-term slices:

- Make rigging recipes more explicit about install steps, env, prompts,
  expected tools, state paths, and cache policy.
- Add reusable example recipes for fff, MCP-style tools, and prompt-only
  variants.
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
- Add a tiny repo-local benchmark adapter for fast CI and docs examples.
- Define an evaluator adapter interface separate from native benchmark
  launchers.
- Defer LLM/code-quality evaluators until the benchmark path is stable, but
  keep report and artifact shapes open to advisory evaluators.

## 5. Repeated Runs and Result Quality

Goal: YACHT can support publication-quality or database-quality comparisons.

Near-term slices:

- Model trials/repetitions explicitly.
- Report variance, pass rates, failure rates, cost distributions, and tool-use
  distributions across repeated runs.
- Preserve per-trial logbooks while producing aggregate scorecards.
- Add controls for task sampling and randomization.
- Make it clear that LLM outcomes are observations, not deterministic cached
  facts.

## 6. Ecosystem Readiness

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
