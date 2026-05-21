# Project Vision

YACHT is an evaluation control plane for agentic coding systems.

It should help people answer whether a coding-agent setup is actually better,
not merely whether it looks better in a demo. A setup can include a model,
agent harness, runtime image, prompts, tools, MCP servers, memory systems,
skills, credentials policy, and task strategy. YACHT gives those pieces a
versioned shape, runs them under controlled conditions, and preserves the
evidence needed to compare results.

## North Star

YACHT should be a testbed for evaluating almost any coding-agent setup, within
reasonable isolation and reproducibility limits, against a controlled baseline.

A tester should be able to define:

- a baseline setup, such as a stock agent harness or their current production
  stack
- one or more challenger setups, such as a new tool, MCP server, prompt pack,
  skill set, CLI, runtime image, model, or harness policy
- a course, such as a public benchmark, benchmark subset, smoke suite, or
  custom eval
- the evidence required to trust that each setup was actually available,
  configured, isolated, and used as claimed

YACHT's job is to run those setups through the same course, preserve the wake,
delegate grading to benchmark-native harnesses when appropriate, normalize the
results, and make the comparison legible.

The long-term goal is not "Pi+fff on one SWE-bench Lite task." That path is the
first real proof that the control plane can run a trusted comparison. The
project should steadily generalize from that proof into a benchmark and custom
eval workbench for harnesses, tools, prompts, runtimes, and evaluator adapters.

## Users

YACHT should serve several audiences:

- Tool builders testing whether their tool improves coding-agent outcomes.
- Agent teams comparing models, prompts, harness policies, and runtime images.
- Researchers running reproducible evaluations.
- Teams deciding whether a proposed coding-agent setup is reliable enough for
  real workflows.

## Project Promise

YACHT should make a comparison legible:

- What was tested?
- What changed between variants?
- Was each environment valid before spending tokens?
- What did each agent produce?
- How was it graded?
- What did it cost in tokens, dollars, time, failures, and tool calls?
- Which artifacts prove the result?

The scorecard is the visible output, but the logbook is the core artifact. A
good logbook is inspectable enough for local debugging and structured enough
for other tools to index, compare, and publish.

## Core Evaluation Unit

The core unit is a comparison among vessels on a course.

- A **vessel** is a full setup being evaluated: harness, model, runtime,
  prompts, tools, skills, MCP servers, memory, secrets policy, and task
  strategy.
- A **baseline** is the tester's chosen control. It is commonly a stock setup,
  but it may also be the tester's current stack.
- A **challenger** is a setup that changes one or more declared surfaces.
- A **course** is the task set and evaluator path used to generate observations.
- A **logbook** is the durable artifact trail that makes the comparison
  inspectable.

YACHT should not assume one universal baseline. The baseline is part of the
experiment design and must be explicit in the regatta.

## Evaluation Scope

YACHT should support several evaluator families:

- Native benchmark harnesses such as SWE-bench.
- Small smoke courses for verifying runtime and tool behavior.
- Custom task suites owned by teams.
- LLM/code-quality evaluators that produce structured reports.
- Human-review or hybrid evaluators.

Only some evaluators are ground truth. YACHT should clearly distinguish
benchmark-grade results from advisory evaluations while making both easy to add
and compare.

## Trust Model

Agent attestation is not enough. YACHT should collect machine evidence:

- command availability
- environment variables
- isolated runtime paths
- setup command output
- transcript paths
- tool calls
- runtime snapshots
- candidate patches
- native grading reports

Preflight determines whether a run is valid to execute. Grading determines how
well a valid run performed. Reports must keep those concerns separate.

## Strategic Priorities

YACHT should prioritize work that expands what can be credibly evaluated.

The current priority order is:

1. Generalize task and course selection beyond the first Django SWE-bench Lite
   smoke.
2. Generalize harness configuration so Pi is one harness, not the implicit
   architecture.
3. Generalize rigging so tools, CLIs, MCP servers, skills, prompt packs, env,
   config files, and setup commands can be modeled without fff-specific
   assumptions.
4. Add at least one more harness adapter to prove the model.
5. Add at least one non-SWE-bench custom eval adapter to prove YACHT is not only
   a benchmark wrapper.
6. Keep containerized runtime isolation, explicit secrets, and machine
   preflight evidence central to any trusted eval claim.

Report and CLI polish are valuable when they help users run, trust, inspect, or
extend real evals. They should not displace work that broadens harnesses,
rigging, runtimes, courses, or evaluator adapters.

## Prioritization Guardrails

A slice is on-mission when it materially improves at least one of these:

- supports another harness, tool surface, runtime backend, benchmark, task
  selection mode, or custom evaluator
- improves trust in eval validity through isolation, preflight, provenance, or
  artifact quality
- makes a real benchmark or custom eval easier to run without hiding important
  evidence
- preserves or improves the language-neutral logbook contract
- reduces hardcoded assumptions about Pi, fff, SWE-bench Lite, or a specific
  task

A slice is likely a side quest when it mainly:

- perfects a CLI/report surface that already works well enough for current eval
  runs
- adds demo polish without expanding or validating the testbed
- hardcodes a personal workflow or local tool into public project behavior
- optimizes around one harness, one tool, one benchmark, or one task in a way
  that makes generalization harder
- treats advisory LLM judging as ground truth rather than one evaluator family
