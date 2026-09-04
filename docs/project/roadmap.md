# Roadmap

This roadmap is organized around making YACHT useful as an open-source tool for
reproducible coding-agent evaluation.

The project north star is a general testbed for evaluating coding-agent setups
against controlled baselines across public benchmarks and custom evals. Work
that expands harnesses, rigging, runtime trust, course selection, and evaluator
adapters should take priority over polishing a single Pi+fff smoke path.

## Where work is tracked

Roadmap outcomes and the product backlog live in the Plane project **YACHT**.
Granular execution of an in-flight change is tracked in the Kata project
`yacht`. Provider configuration is committed in `.sjujperpowers/config.json`.

Versioned design artifacts stay in this repository:

- `docs/adr/` — architecture decisions (authoritative for approved behavior)
- `docs/project/specs/` — approved designs; each carries `**Outcome:** plane:YACHT-N`
- `docs/project/plans/` — implementation plans; each carries `**Source:** plane:YACHT-N`
- `docs/project/0.NN-*.md` — release plans (pre-Plane format, retained as written)

## Release outcomes

| Outcome | Release | State |
| --- | --- | --- |
| Episodic trials in a persistent task workspace (ADR 0025) | pre-0.11 | Done |
| MCP installs through capability-providing riggings (ADR 0024) | pre-0.11 | Done |
| [OMP and Codex first-class harnesses](plans/omp-codex-harness-expansion.md) | 0.11.0 | Done |
| [Durable Logbooks](0.12-durable-logbooks.md) | 0.12.0 | Done |
| [Reproducible Task Sampling](0.13-reproducible-sampling.md) | 0.13.0 | In Progress |

Yacht 0.13 is implemented and its release candidate has passed every
token-free gate. It ships once the live provider release gate
(`scripts/release_gate.py`) passes.

## Themes

The nine themes below describe what YACHT already does and where each area can
still grow. The "remaining" work for every theme is an open Plane work item;
this file no longer duplicates that backlog. No post-0.13 outcome has been
selected. Choose one only when the next concrete evaluation or consumer
establishes the priority.

### 1. Generalized Benchmark Surface

YACHT selects SWE-bench instances explicitly, from reusable task-set files,
with an ordered `max_instances` cap, or as a seeded random sample under the
language-neutral `sha256-rank-v1` contract. Selected tasks and population
provenance survive into plans, handoffs, runbooks, Scorecards, and reports.
Native SWE-bench Docker grading remains the source of benchmark truth.

### 2. Harness Generalization

Harness kind is explicit. Pi, Claude Code, OMP, Codex, declared, and
local-smoke harnesses share one task-attempt and reporting contract; the
Pi-specific smoke command is retired.

### 3. Recipes and Rigging

Named setup, environment, prompt, tool, cache, config-file, skill, and MCP
changes are modeled with capability checks before execution. Rigging and
resolved tool provenance are recorded in task artifacts and reports.
Organization-specific recipes and secret coordinates stay outside the public
examples.

### 4. More Benchmark and Evaluator Adapters

Course and evaluator seams are exercised by SWE-bench, Terminal-Bench,
LiveCodeBench, Aider Polyglot, custom evals, and repository-local smoke
workflows. Native harnesses own execution and grading; Yacht owns normalized
handoffs, evidence, and Scorecards. Production workflows use the split Course
and evaluator registries; the combined `benchmark_adapter()` facade remains only
for compatibility.

### 5. Runtime Trust and Preflight Evidence

Container runtimes are the trusted path; host Nix is a development backend.
Execution is gated on runtime, harness, Rigging, tool, path-isolation, secret,
and agent-prompt evidence before task tokens are spent.

### 6. Repeated Runs and Result Quality

Repetitions are a parent Logbook with indexed child Logbooks. Per-run
Scorecards are preserved and aggregate JSON and Markdown reports are produced.
LLM outcomes are labeled as observations, not deterministic cached facts.

### 7. Logbook as Durable Artifact

A portable, versioned run index records lifecycle state, identity, comparisons,
artifacts, timestamps, generated reports, and child Logbooks. The shared reader
is authoritative for status, report, latest-run selection, and dashboard
discovery.

### 8. First-Run UX

`yacht doctor`, supported smoke examples, full-run commands, generated
runbooks, actionable next commands, and Logbook-contained native artifacts are
shipped. Token-free local smoke paths remain available for contributor and
release checks.

### 9. Ecosystem Readiness

Schema versions are explicit and language-neutral, and public JSON Schemas ship
in the wheel. The remaining consolidation — moving handwritten structural
validators onto the packaged schema loader one artifact family at a time — is
tracked in Plane.

## History

Completed release outcomes live in the versioned release plans and the
changelog. The July 2026 audit and its closure are recorded in
[Audit follow-ups](audit-followups.md).
