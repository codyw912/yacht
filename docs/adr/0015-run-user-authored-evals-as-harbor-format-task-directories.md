# ADR 0015: Run User-Authored Evals as Harbor-Format Task Directories

## Status

Proposed

## Context

YACHT's course roster is benchmarks other people published. The point of
the project — validating claims about harnesses, tools, and extensions —
ultimately requires evals users write themselves: the recurring failure
mined from production traces, the ability a tool vendor claims, the
regression a team wants pinned down. The registered `custom-eval` kind
does not serve this; it is internal scaffolding that exercises the
pipeline against a mock local harness, not an authoring surface.

The question is what format user-authored evals take. Writing our own
task format would mean also writing its environment builder, executor,
and verifier protocol — and asking contributors to learn a format only
YACHT reads. Meanwhile the Harbor task format (an instruction, a
Dockerfile environment, a verifier) is becoming the interchange for
exactly this work: LangChain's Eval Engineering Skill has coding agents
mine a repository and traces, interview the user, and emit executable
evals in Harbor format; agent-workflow frameworks build the same
propose–approve–build loop against Harbor tasks. An ecosystem of tools
that *generate* evals is forming, and it emits a format we already run:
the 0.4.0 foundation (ADR 0012) executes Harbor-format courses through a
pinned launcher with yacht-owned agents, typed rigging, install-only
preflight, and normalized native reports. Harbor's job configuration
accepts a local task directory (`DatasetConfig.path`) as a first-class
dataset source alongside registry pins, so nothing about the foundation
assumes tasks come from a registry.

ADR 0012 named the task format as the documented exit and committed us
to keeping a non-Harbor course maintained; LiveCodeBench (ADR 0014) now
holds that line. Adopting the Harbor task format for user-authored evals
is therefore consistent with the independence guards rather than in
tension with them.

One rule does not transfer directly. Registered courses pin datasets by
content-addressed registry reference; a directory on the user's disk has
no such pin, so provenance and comparability need a different anchor.
And the eval-authoring ecosystem's own experience reports the failure
mode we must surface: first-draft verifiers are rarely right, and agents
reward-hack them — overciting to collect credit, claiming actions never
taken, exploiting exposed answer material. Catching this requires
inspecting what the verifier did, not just the score it produced.

## Decision

We will make user-authored evals a Harbor-format course: a course kind
whose dataset is a local directory of Harbor-format tasks, run through
the existing launcher foundation.

- **The authoring surface is the Harbor task format, not a YACHT
  format.** A custom course points at a directory of tasks — each an
  instruction, an environment Dockerfile, and a verifier — and YACHT
  treats it exactly as it treats a registry-pinned Harbor course: native
  rollout through the pinned launcher image, yacht-owned agents applying
  typed rigging inside task containers, install-only preflight, trial
  results normalized into the standard grading report. Evals authored by
  hand or emitted by external generation tooling run unmodified.
- **Authoring stays out of scope.** YACHT does not propose, generate, or
  revise evals. The ecosystem is building that loop — mine traces,
  propose abilities, interview the user, emit tasks — and its output is
  our input. YACHT's contribution is what generation tooling does not
  provide: hermetic pinned execution, statistical verdicts (ADR 0013),
  and provenance-filtered aggregation over the results.
- **The content hash is the pin.** With no registry reference to record,
  YACHT hashes the task directory's contents and records the digest in
  the adapter configuration and every downstream artifact, alongside the
  resolved task list. Runs are comparable when their digests match, and
  a changed eval is visibly a different eval — the same property the
  registry pin provides, anchored in content instead of a registry.
- **Verifier evidence is a first-class artifact.** Task-attempt
  artifacts for custom courses preserve the verifier's trajectory —
  its commands, output, and reasoning where the trial records them —
  not just the reward. First-draft verifiers fail by crediting the
  wrong thing, and the revision loop runs on seeing what was credited;
  a score alone hides exactly the reward hacking users need to catch.
- **The mock retires from the registry.** The current `custom-eval`
  kind and its local mock harness leave the registered roster; whatever
  pipeline tests still need a synthetic course use test fixtures, not a
  user-facing kind. The name is reused for the real course so configs
  read as intended: `kind = "custom-eval"`, harness `harbor`, dataset a
  local path. This is a breaking change to a kind that was never useful
  outside YACHT's own tests, made before 1.0.

## Consequences

- User-authored evals inherit the entire 0.4.0–0.5.0 surface on day
  one — pinned launcher, rigging, install-only preflight, normalized
  reports, statistics, provenance, dashboard — instead of waiting on a
  parallel custom-format stack.
- YACHT plugs into the eval-generation ecosystem at a clean seam: tools
  that emit Harbor-format tasks gain a rigorous runner, and YACHT gains
  an authoring story without owning generation.
- The course/evaluator seam is now maintained by real user-facing needs
  rather than only benchmark adapters — the reason to build this sooner
  rather than later.
- Trust shifts from "pinned registry content" to "hashed local content":
  YACHT guarantees the run matches the digest, but the tasks themselves
  are the user's responsibility, and task environments still execute
  arbitrary Dockerfiles under the launcher's container boundary — the
  same standing as any Harbor dataset, now with a user-authored source.
- Verifier-trajectory capture depends on what Harbor trials record;
  where the harness records less than we want, the gap is documented
  rather than papered over.
- Removing the mock kind breaks configs that referenced `custom-eval`,
  none of which exist outside YACHT's own tests and examples.
- The Harbor task format's evolution now affects user-authored evals
  directly; the pinned launcher version bounds the blast radius, and
  format migration remains the documented exit (ADR 0012).
