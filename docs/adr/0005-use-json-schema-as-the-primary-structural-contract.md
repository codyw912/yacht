# ADR 0005: Use JSON Schema as the Primary Structural Contract

## Status

Accepted

## Context

YACHT persists regatta configuration, preflight evidence, task attempts,
runtime snapshots, benchmark handoffs, grading reports, scorecards, and logbook
state as JSON artifacts. Those artifacts are part of the product surface: a
user should be able to run a small credible benchmark locally, inspect the
logbook, and use the resulting evidence outside the Python process that
produced it.

The packaged public schema files under `src/yacht/schemas/` already describe
that cross-language contract. The reference docs also identify them as YACHT's
durable contract because Python is the current control-plane implementation,
not a requirement for consumers of persisted artifacts.

At the same time, `yacht.contracts.schemas` has grown into a large handwritten
validator that mirrors much of the same structural contract. It also imports
adapter and runtime knowledge from `yacht.courses` and `yacht.runtimes`, which
makes the contracts module depend on higher-level implementation modules. That
increases the cost of adding another course or evaluator adapter and risks
making the handwritten validator the long-term source of truth by default.

YACHT still needs Python validation. JSON Schema is a good fit for structural
checks, but some rules are semantic: cross-field consistency, dynamic adapter
and capability checks, redaction invariants, summary totals matching detail
rows, and user-facing error normalization.

## Decision

YACHT will treat the JSON Schema files in `src/yacht/schemas/` as the primary
structural contract for persisted artifacts and regatta configuration.

Python validators remain part of the public interface for the control plane,
but their role is narrowed:

- load and cache the matching JSON Schema file
- run structural validation against that schema
- run semantic validation that JSON Schema cannot express cleanly
- preserve the current `SchemaValidationError` and `ConfigError` ergonomics for
  callers

The existing validator functions, such as `validate_regatta_document()` and
`validate_task_attempt_document()`, remain the call-site interface during the
migration. Their implementation should move toward schema-first validation
rather than more handwritten structural checks.

Dynamic validation knowledge, such as supported course adapter kinds, supported
harnesses, and built-in runtime tool capabilities, must be supplied to the
contracts module through a validation context or caller-provided parameters. The
contracts module should not import from `yacht.courses`, `yacht.runtimes`, or
other higher-level implementation modules.

New persisted artifact families should start with a public schema file. Any
Python validation added for that artifact should be limited to semantic checks
or clearer error reporting.

## Consequences

YACHT's durable artifact contract stays language-neutral. Local users, hosted
services, and external tools can validate logbooks and scorecards without
embedding YACHT's Python implementation.

The migration should be incremental. Existing call sites should continue to use
the current validator functions while artifact families move behind
schema-first validation one at a time. A low-risk artifact family should be used
as the first slice before migrating regatta configuration or benchmark
scorecards.

Splitting `yacht.contracts.schemas` into multiple handwritten validator modules
is not the destination. Small helper modules are acceptable if they support the
schema-first design, but the long-term goal is to shrink handwritten structural
validation, not preserve it in smaller files.

The contracts module becomes a deeper module with a smaller interface: callers
ask whether a document satisfies a named YACHT contract, while schema loading,
structural validation, semantic checks, and error normalization stay behind
that interface.

Adding a new course or evaluator adapter should not require editing structural
artifact validation unless the adapter introduces a new artifact schema. Adapter
registration and dynamic adapter checks belong at adapter seams, not as static
imports inside the contracts module.
