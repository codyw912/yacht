# ADR 0012: Run Harbor-Format Courses with Yacht-Owned Agents in a Pinned Launcher

## Status

Proposed

## Context

The Terminal-Bench course (ADR 0011) delegates rollout and verification to
Harbor. Implementing it exposed three problems the first integration
accepted for expedience.

First, Harbor's built-in agents own the thing YACHT exists to measure.
Harbor decides how the harness is installed and configured inside the task
container, so YACHT's harness adapters and typed rigging steps (ADR 0008)
are bypassed for this course, and vessels are limited to agents Harbor
ships, configured Harbor's way. Second, the orchestrator is a host process:
`harbor run` executes through uv with run-time dependency resolution and
the host environment in scope — and the SWE-bench grading launcher shares
this defect. Third, Terminal-Bench vessels must declare a `host-nix` or
`container` runtime that YACHT never executes, inventing flakes and
commands to satisfy validation.

Surveying the ecosystem before fixing this changed its weight. The Harbor
registry hosts roughly eighty benchmark datasets in one open task contract
— a directory of `task.toml`, instruction, environment Dockerfile, and a
verifier script producing a reward — including both of the roadmap's named
next courses (all 225 Aider Polyglot exercises; a LiveCodeBench subset)
and SWE-bench variants. Every registry dataset version pins each task to a
git URL, commit, and path, so a version reference is content-addressed.
Adapters ship parity experiments measuring fidelity to the original
benchmark's scoring. And Harbor's agent interface is a public extension
point: any class implementing its installed-agent contract can perform the
in-container install and run phases.

## Decision

We will rebuild the Harbor integration so that YACHT owns what is being
measured and Harbor provides environments and verification.

- **Yacht-owned agents.** YACHT ships Harbor agent classes for its
  harnesses, loaded via Harbor's custom-agent import path. Their install
  phase applies the vessel definition — the pinned harness version, then
  YACHT's typed rigging steps — inside the task container; their run phase
  reuses Harbor's harness-running logic where practical. Rigging semantics
  are therefore identical across yacht-run and native-rollout courses, any
  harness YACHT models can run, and provenance records the agent
  implementation that produced each trial.
- **A pinned launcher image.** The orchestrator moves into a YACHT-built
  container image with Harbor, its locked dependencies, and YACHT's agent
  classes baked in at build time — no run-time resolution. It mounts the
  Docker socket to start sibling task containers and receives only
  explicitly declared secrets. This is the same trust move as ADR 0004,
  applied to native launchers; the SWE-bench grading launcher should
  follow. Socket access is a stated limit: the launcher is isolated except
  for Docker control.
- **A shared Harbor-course foundation.** The course machinery built for
  Terminal-Bench — job rendering, roster, native launcher, reward
  translation, attempt synthesis — becomes dataset-parameterized. Adding a
  Harbor-format course is a registry reference, task selection, and
  documented scoring caveats; `terminal-bench` is the first named course
  on the foundation, Aider Polyglot and others follow as configs. Configs
  pin dataset versions, and full determinism can additionally pin a
  registry snapshot.
- **The `harbor` backend becomes honest.** A third runtime backend names
  the launcher chain: YACHT runs the launcher image (the recipe's real,
  versioned `image`), which runs Harbor, which runs task containers with
  the vessel's agent installed inside. The recipe carries `harness`, a
  required `harness_version`, secrets, env, and preflight — no flake, no
  ceremonial command. An `install-only` preflight check runs Harbor's
  install-only trial mode, proving agent-plus-rigging installation in a
  real task container at zero token cost. Capability preflight gates
  rigging methods to what the agent layer can apply.

Independence from Harbor is a design constraint, not an afterthought:

- YACHT's artifact schemas remain the contract. Harbor courses produce
  grading reports, task attempts, and provenance by translation, exactly
  as SWE-bench does; nothing downstream knows which launcher ran.
- Official native harnesses remain the source of grading truth where they
  exist. The SWE-bench official path stays first-class and exercised;
  Harbor's SWE-bench adaptation does not replace it. Harbor-course results
  are adaptation numbers and carry their parity evidence.
- The task format is the documented exit: pinned task directories are
  runnable by a future YACHT-native environment runner without config
  changes if Harbor ever drifts or turns hostile.
- The catalog must not atrophy the non-Harbor muscle. The roadmap keeps at
  least one major course integrated outside the Harbor ecosystem beyond
  SWE-bench — LiveCodeBench through its official evaluation harness is the
  named next target — so the course/evaluator seam stays proven against
  contracts we do not choose.

## Consequences

- One integration opens a large course catalog, and per-benchmark work
  drops to configuration plus documentation; the tool-claim workflow gains
  many surfaces at once.
- Runs use YACHT's agent classes, not Harbor's stock agents, so results
  are not byte-comparable to public leaderboard entries; internal
  baseline-versus-rigged comparisons — YACHT's purpose — get stronger,
  and provenance makes the difference inspectable.
- Harbor's installed-agent interface is the tightest coupling and can
  drift; it is pinned inside the launcher image, upgraded deliberately,
  and confined to a thin module whose rigging knowledge lives in YACHT's
  own step model.
- The backend enum grows to three, but each value now names something
  YACHT actually executes; the ceremonial-runtime wart and the earlier
  "metadata-only backend" framing of this ADR's first draft are both
  superseded.
- The gravitational risk is discipline, not lock-in: because Harbor makes
  courses cheap, defaulting every benchmark to its adaptation would erode
  the native-truth principle. The guards above — official paths
  first-class, parity evidence surfaced, a maintained non-Harbor course —
  encode the discipline this ADR expects reviews to hold.
