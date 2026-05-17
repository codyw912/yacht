# ADR 0004: Use Containerized Agent Runtimes for Trusted Eval Execution

## Status

Accepted

## Context

The initial `host-nix` runtime backend proved the Pi baseline versus Pi+fff
preflight path, but it also exposed host-environment risk. Pi was discovered
from the host `PATH`, `pi install` initially interacted with host npm/mise
state, and YACHT had to add defensive npm and cache isolation to keep setup
inside the trial runtime.

That is acceptable for local development, but it is not a strong enough
foundation for trusted eval claims. Agent runtime isolation needs to be explicit
and reproducible before YACHT spends real benchmark tokens or compares tool
variants.

## Decision

YACHT will make containerized agent runtimes the trusted execution target.
`host-nix` remains available as a fast development backend, but container
runtimes are the path for credible smoke runs, shared evals, and reproducible
execution.

Container runtimes are still separate from benchmark task environments:

- The agent runtime container runs Pi, Codex, Claude, MCP servers, extensions,
  prompts, explicit secrets, and per-trial tool state.
- Native benchmark harnesses, such as SWE-bench Docker grading, continue to own
  benchmark task containers, test execution, and grading.

The container runtime contract includes:

- a declared image reference
- a declared runtime command
- an isolated container `HOME`
- a mounted workspace path
- a mounted per-trial runtime state path
- explicit secret injection only
- rigging setup executed inside the container runtime
- preflight evidence for command availability, resolved env, isolated paths,
  setup commands, transcripts, and tool-call evidence

The public abstraction remains `RuntimeBackend`, not a Docker-specific runner,
so future backends can use Nix-built images or remote workers without changing
regatta concepts.

## Consequences

The next implementation path should prioritize a `container` backend over
further hardening of `host-nix`. The first slice defines the config and dry-run
contract. Follow-up slices should build or reference a Pi runtime image, execute
machine preflight in `docker run`, apply Pi+fff rigging inside the container,
and then run the first real task smoke through the same backend.

Container execution introduces Docker/image concerns earlier: image build or
pull behavior, workspace mount ownership, network policy, cache strategy, and
interaction with benchmark-native Docker harnesses. Those concerns are the right
ones to solve now because they determine whether eval observations are
reproducible and trustworthy.
