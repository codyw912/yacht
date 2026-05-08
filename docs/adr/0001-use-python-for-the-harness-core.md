# ADR 0001: Use Python for the Harness Core

## Status

Accepted

## Context

YACHT needs a control plane for reproducible evaluations of agentic coding setups. The core workflow is orchestration-heavy: load experiment configuration, run vessels against courses, collect wake artifacts, compute metrics, persist scorecards, and support later analysis.

The main expected bottlenecks are model latency, agent runtime, repository setup, test execution, sandboxing, and artifact I/O. Raw CPU performance inside the harness is not expected to dominate early YACHT workloads.

The primary alternatives considered were Python, Go, Rust, and TypeScript/Node.

## Decision

Use Python as the YACHT harness core language.

Python is the best current fit for experiment orchestration, metrics, statistics, report generation, and fast iteration on evaluation methodology. It also has strong ergonomics for subprocess control, structured artifacts, TOML/JSON processing, and later data analysis.

YACHT's stable contract should not be Python-specific. The durable boundary is:

- configuration in
- wake artifacts out
- scorecards and logbook records persisted in language-neutral formats

Vessels and rigging integrations should be able to run out-of-process through adapters, subprocesses, or containers. They must not need to be in-process Python plugins.

## Consequences

Python remains a defensible default while YACHT is still discovering its evaluation model.

We should:

- keep persisted artifacts language-neutral
- avoid Python-only serialized state such as pickle
- define explicit schemas for courses, vessels, regattas, wake artifacts, and scorecards
- preserve subprocess/container adapter boundaries for non-Python vessels
- treat Python as the control plane, not as a requirement for every evaluated setup

This decision does not rule out adding a hardened runner later in Go or Rust if YACHT needs single-binary distribution, stronger process supervision, tighter sandboxing, or higher-throughput execution.

TypeScript/Node is not selected for the harness core because its main advantages are stronger for web UI and JavaScript ecosystem integration than for YACHT's current control-plane and analysis needs. A future web scorecard or UI can still be built in TypeScript without moving the harness core.
