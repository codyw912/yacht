# Codebase Structure

YACHT is organized around its extension seams:

- `yacht.domain` contains the core concepts: regattas, courses, vessels,
  runtimes, rigging, preflight checks, task attempts, wakes, and scorecards.
- `yacht.config` loads and expands regatta configuration into domain objects.
- `yacht.runtimes` resolves and prepares runtime adapters such as `host-nix`
  and `container`.
- `yacht.harnesses` contains agent harness adapters such as Pi and local smoke.
- `yacht.courses` contains course and evaluator adapters such as SWE-bench and
  custom evals.
- `yacht.preflight` executes machine and agent preflight evidence collection.
- `yacht.workflows` composes end-to-end smoke, benchmark, launch, and runbook
  workflows.
- `yacht.reports` renders scorecards, status views, readiness reports, and
  aggregate reports.
- `yacht.logbook` owns shared logbook artifact I/O and common artifact paths.

Top-level modules such as `yacht.regatta`, `yacht.pi_adapter`, and
`yacht.benchmark_scorecard` are compatibility shims. New code should import
from the package that owns the behavior.
