# ADR 0012: Add a Harbor Runtime Backend for Native-Rollout Courses

## Status

Proposed

## Context

The Terminal-Bench course (ADR 0011) delegates rollout and verification
to Harbor, but its vessels still must declare a `host-nix` or
`container` runtime — the only two backends YACHT knows. That runtime is
never executed: YACHT does not launch the vessel's command, enter its
flake, or run its image. The recipe exists only to carry metadata the
course actually needs — the harness name, the pinned `harness_version`,
required secrets, and preflight checks.

The ceremony is not free. A Terminal-Bench vessel must invent a `flake`
or `image` and a `command` to satisfy backend validation, which reads as
meaningful configuration and is not. Preflight command checks execute
through the backend's wrapper — `nix develop <flake> --command` for
host-nix — so a config that only wants to check `docker info` on the
host acquires a hard nix dependency. And the strongest preflight
evidence available for this course is not expressible at all: Harbor's
install-only trial mode, which installs the pinned agent and its rigging
into a real task container and exits before any tokens are spent —
validated live during the ADR 0011 work, and exactly the
machine-evidence-before-spend bar that ADR 0003 set.

## Decision

We will add a third runtime backend, `harbor`, for vessels whose course
performs a native rollout.

- **Metadata, not execution.** A `harbor` runtime declares `harness`
  and a required `harness_version`, plus optional env, required
  secrets, and preflight. It has no `command`, `flake`, or `image` —
  backend validation rejects them rather than requiring them. The
  execution environment is the task's own container, owned by Harbor;
  the recipe stops pretending otherwise.
- **Course and backend must agree.** A `harbor` runtime is valid only
  on native-rollout courses, and the `terminal-bench` course requires
  it; a config pairing a harbor vessel with SWE-bench, or a host-nix
  vessel with Terminal-Bench, fails validation with an actionable
  error. The example configs migrate off their ceremonial host-nix
  runtimes.
- **Preflight runs on the host, plus install-only trials.** Command
  and env checks for harbor vessels execute directly on the host with
  no wrapper — they are host-prerequisite checks (Docker up, harbor
  resolvable), not environment probes. A new `install-only` preflight
  check kind runs Harbor's install-only trial for the vessel's pinned
  agent and rigging against the course's first task, producing real
  machine evidence — the resolved installed version from
  `agent_info` — at zero token cost. The evidence lands in the
  preflight artifact like any other check.
- **Capabilities gate the same way.** The rigging install methods a
  harbor backend supports are exactly those the Terminal-Bench job
  renderer can express (`mcp-server`, plus rigging env); anything else
  is blocked by capability preflight before tokens are spent, with the
  render-time check remaining as the second line of defense.
- **Provenance and instances simplify.** Runtime instance resolution
  for harbor vessels records the backend and logbook-scoped evidence
  paths without temp homes, command prefixes, or cleanup obligations,
  and attempt synthesis (which already stamps `backend: "harbor"`)
  stops diverging from the declared runtime.

## Consequences

- Terminal-Bench configs shrink to what they mean: harness, pinned
  version, model, rigging, secrets, and checks. No invented flakes,
  commands, or nix dependency for users who only run this course.
- Preflight for native-rollout courses gains its missing strong check:
  agent-plus-rigging installation proven in a real task container
  before spend, closing the loop ADR 0011 opened with install-only
  trials.
- The backend enum grows to three everywhere it is validated — config
  schema, capability tables, runtime instances, doctor — and each
  existing site must decide what `harbor` means there rather than
  inheriting container semantics silently.
- Install-only preflight invokes Harbor (and Docker) during the
  preflight stage, which is slower than command checks; it is a
  declared check, so cost-sensitive configs can omit it, accepting
  weaker evidence.
- A future native-rollout course reuses the backend as-is; if one ever
  needs course-specific runtime metadata beyond harness and version,
  that is a new field on the recipe, not a new backend.
