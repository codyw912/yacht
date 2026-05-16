# Product Vision

YACHT is an evaluation control plane for agentic coding systems.

It should help people answer whether a coding-agent setup is actually better,
not merely whether it looks better in a demo. A setup can include a model,
agent harness, runtime image, prompts, tools, MCP servers, memory systems,
skills, credentials policy, and task strategy. YACHT gives those pieces a
versioned shape, runs them under controlled conditions, and preserves the
evidence needed to compare results.

## Users

YACHT should serve several audiences:

- Tool builders testing whether their tool improves coding-agent outcomes.
- Agent teams comparing models, prompts, harness policies, and runtime images.
- Researchers running reproducible public or private evaluations.
- Teams deciding whether a proposed coding-agent setup is reliable enough for
  real workflows.
- Future hosted-product users who want managed runs, history, sharing, and
  community evals without operating the local harness directly.

## Product Promise

YACHT should make a comparison legible:

- What was tested?
- What changed between variants?
- Was each environment valid before spending tokens?
- What did each agent produce?
- How was it graded?
- What did it cost in tokens, dollars, time, failures, and tool calls?
- Which artifacts prove the result?

The scorecard is the visible output, but the logbook is the product core. A
good logbook is inspectable enough for local debugging and structured enough
for a hosted service to index, compare, and publish.

## Open Source and Hosted Boundaries

The public repo should remain the engine:

- configuration model
- runtime and rigging recipes
- benchmark/course adapters
- preflight checks
- task attempts
- artifact schemas
- report generation
- local orchestration

A hosted product can layer on:

- managed runner pools
- team and project organization
- secrets management
- scheduled and repeated runs
- public/community result databases
- run history and dashboards
- artifact retention and search
- collaboration, comments, approvals, and publishing workflows

The hosted product should not require a different domain model. It should read
and write the same core YACHT concepts and artifacts wherever possible.

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

