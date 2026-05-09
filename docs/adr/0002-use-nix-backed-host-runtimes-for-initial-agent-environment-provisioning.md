# ADR 0002: Use Nix-Backed Host Runtimes for Initial Agent Environment Provisioning

## Status

Accepted

## Context

YACHT needs reproducible agent runtime setup without taking ownership of every
benchmark's task isolation and grading model. Agent runtimes include tools such
as Pi, Codex, Claude, MCP servers, extensions, prompts, credentials injection,
and tool caches. Benchmark task environments include repository checkout,
container setup, test execution, grading, and benchmark-specific logs.

The first real target is comparing a baseline Pi vessel with a Pi vessel rigged
with fff. fff is useful as an early design target because it touches multiple
runtime surfaces: Pi extension installation, environment variables, MCP-style
tooling, and persistent cache paths. SWE-bench and SWE-bench Lite already have
their own Docker-based task isolation and grading harness, so duplicating that
inside YACHT would add risk before the agent runtime model is proven.

## Decision

YACHT will model agent runtime provisioning separately from task execution.

The initial runtime backend is `host-nix`: YACHT enters a Nix-provided runtime
on the host and prepares isolated per-trial runtime state. Each trial gets a
temporary `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_STATE_HOME`, and
tool-specific paths such as `FFF_FRECENCY_DB` and `FFF_HISTORY_DB`.

The public configuration model uses these concepts:

- `RuntimeRecipe` for a named backend, flake reference, command, environment,
  mounted paths, and required secret references.
- `RiggingRecipe` for named setup/configuration applied to a runtime.
- `RuntimeInstance` for the prepared per-trial runtime state that a future
  backend will create.
- `CourseAdapter` for benchmark-specific task mapping and grading delegation.

Secrets must be referenced explicitly. YACHT may resolve configured secret
references later, but it must not copy credentials or auth state implicitly from
the user's normal home directory. Wake and logbook artifacts should record
redacted references, not secret values.

## Consequences

The first implementation can validate Pi baseline vs Pi+fff configuration
without launching Pi, installing fff, or invoking Docker.

This keeps YACHT focused on its control-plane responsibility while leaving
SWE-bench task containers and grading inside the native SWE-bench harness.
Future backends can add stronger isolation through Nix-built containers, remote
workers, or hosted execution without renaming the abstraction away from
`RuntimeBackend`.
