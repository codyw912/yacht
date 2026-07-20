# ADR 0011: Add a Terminal-Bench Course via the Harbor Harness

## Status

Proposed

## Context

SWE-bench Lite is YACHT's only real benchmark course, and its shape has
quietly become the pipeline's mental model: a task is a repository at a
commit, an attempt produces a candidate patch, and grading is a separate
native Docker harness that replays patches after the fact. The roadmap
names Terminal-Bench as the first post-SWE-bench course precisely to stop
that shape from ossifying into the architecture.

Terminal-Bench breaks the shape on purpose. A task is a containerized
environment — its own image, services, and files — the agent acts *inside*
that environment through a terminal, and a verifier then runs the task's
test scripts in the same environment to produce a reward. There is no
patch to extract and no way to separate the rollout from the environment:
whatever runs the task must install the agent into the task's own
container.

Terminal-Bench 2.0 ships with an official harness, Harbor, that owns
exactly that problem. Harbor resolves a pinned dataset of task
directories, builds each task environment locally under Docker, installs
a named agent into it at a pinned version (Claude Code and Pi — both of
YACHT's harnesses — are built in), passes model and provider credentials
through explicit configuration, runs the verifier, and writes a
per-trial `result.json` recording the agent's resolved name and version,
the model, token and cost totals, phase timings, and the verifier's
reward. Its job configuration also accepts per-agent MCP server entries
and environment variables, and an install-only trial mode that sets up
the agent and exits before any tokens are spent.

YACHT's existing seams fit one half of this. The course/evaluator adapter
split in `yacht.courses.registry` was built for a second course, and the
scorecard consumes any evaluator that emits the normalized grading-report
shape. But the task-attempt stage assumes YACHT's own runtime image and
harness adapter perform the rollout — which Terminal-Bench's model rules
out.

## Decision

We will add a `terminal-bench` course whose native harness is Harbor,
delegating both rollout and verification to it — the same trust pattern
as SWE-bench grading, extended to cover the attempt itself.

- **Harbor is the native launcher.** The course's launcher stage renders
  a Harbor job configuration and runs `harbor run` with a pinned,
  uv-resolved Harbor version, exactly as the SWE-bench course shells out
  to `swebench.harness.run_evaluation`. YACHT never drives Terminal-Bench
  task containers itself.
- **Vessels map onto Harbor agents.** A vessel's harness selects the
  corresponding Harbor installed agent (`claude-code`, `pi`), its pinned
  harness version and model are passed through the job configuration, and
  secrets flow as explicit environment references — never copied state.
- **Rigging maps onto Harbor's agent configuration.** MCP server steps
  render into Harbor's per-agent `mcp_servers` entries and environment
  steps into agent env, reusing the declared-step model of ADR 0008.
  Rigging step kinds Harbor cannot express are blocked by capability
  preflight before tokens are spent, like any unsupported method.
- **Preflight uses install-only trials.** Before the funded run, an
  install-only trial verifies that the agent and its rigging actually
  install into the task environment, giving this course real machine
  evidence at zero token cost.
- **Trial results become YACHT artifacts.** After the run, Harbor's
  per-trial `result.json` is translated into the normalized grading
  report the scorecard already consumes (reward → resolved), and into
  task-attempt artifacts carrying the same usage, outcome, and provenance
  fields as harness-run attempts — with harness version, model, tokens,
  cost, and duration resolved only from what Harbor recorded, null when
  absent, per ADR 0009.
- **Selection stays explicit and pinned.** The course pins the dataset
  version and names its tasks explicitly (with the same bounded-subset
  controls as SWE-bench); no floating "latest" dataset references.

Shared grading and artifact helpers currently living under
`courses/swe_bench/` are lifted into a course-neutral module first, so the
third course does not become a third near-copy.

## Consequences

- YACHT validates tool claims in a second benchmark shape — interactive
  terminal tasks — and the course/evaluator interfaces are proven against
  a course with no repository, no patch, and no separable grading step.
- The task-attempt stage learns that some courses produce attempts from
  native trial evidence instead of running a YACHT harness adapter; this
  is a real pipeline change, not just a new adapter registration.
- The rollout trust boundary moves: for this course, the agent runs in
  Harbor-built task containers rather than YACHT's own pinned runtime
  images. We accept Harbor's environment pinning and recorded evidence as
  the reproducibility story, keep every trial directory in the logbook
  for inspection, and pin Harbor itself like any native harness.
- Config generalizes slightly: `dataset`/`split` semantics become
  adapter-defined, and tasks gain course-specific fields beyond the
  SWE-bench set.
- Harbor is a heavier dependency than the SWE-bench harness — it is also
  an agent runner — and its agent implementations evolve with the
  harnesses they install. Pinning its version in the launcher makes that
  drift visible in provenance instead of silent.
- Running YACHT's harness adapters inside Terminal-Bench task containers
  was rejected: it would rebuild Harbor's agent-installation layer to end
  up less faithful to the benchmark's official execution path. Likewise,
  reimplementing Terminal-Bench tasks as a custom-eval course would forfeit
  native verification as the source of benchmark truth.
