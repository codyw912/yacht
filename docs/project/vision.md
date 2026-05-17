# Project Vision

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
