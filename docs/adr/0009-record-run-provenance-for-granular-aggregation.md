# ADR 0009: Record Run Provenance for Granular Aggregation

## Status

Proposed

## Context

A YACHT verdict is only as meaningful as the description of what produced
it. Most of that description is already captured somewhere in the wake, but
it is scattered and unstructured: the runtime image tag pins the harness
version, machine evidence carries the API-reported model id, setup results
record pinned tool install targets, and the vessel's `model` field is a
config alias that may differ from what the provider actually served.
Nothing ties these together as queryable facts about a run.

That gap blocks two things. First, aggregation: users want scores grouped
at a chosen granularity — all runs of a harness and model regardless of
minor version, or only runs of an exact harness release against an exact
model snapshot — and the aggregate reports cannot filter on dimensions
that only exist as substrings inside evidence blobs. Second, honesty:
when runs that differ in harness, tool, or model version land in the same
aggregate, the report should say so instead of averaging silently, and it
cannot warn about a difference it does not record.

The tool-claim workstream sharpens the need: a validated claim is a
sentence with versions in it — this tool at this version, on this harness
at this version, with this model, changed the outcome by this much.

## Decision

We will record a structured `provenance` block on task attempts and carry
it through to scorecards and aggregates.

- **Contents.** Per attempt: the harness (name plus resolved version), the
  model (configured alias plus the API-reported id from machine evidence),
  the tools carried by the rigging (name, pinned version, and source
  extracted from install targets and setup results), the runtime backend
  and image reference, and the YACHT version that produced the artifact.
- **Resolution reuses existing evidence.** Versions come from what runs
  already produce — the image tag, the pinned `command` version check that
  preflight executes, the machine-evidence model id, and pinned install
  targets. No new probes are added for provenance's sake.
- **Recorded, never guessed.** A version that cannot be resolved from
  evidence is recorded as null. Provenance states what is known and where
  it came from; it does not infer.
- **Granular aggregation.** Aggregate reports gain filtering and grouping
  on provenance dimensions with hierarchical matching — harness name
  before exact version, model family before exact snapshot — so overall
  scores and version-exact scores are both one query over the same
  artifacts.
- **No silent mixing.** When artifacts in one aggregate differ on a
  provenance dimension, the report labels the mix on that dimension
  rather than presenting a blended score as homogeneous.

## Consequences

- The task-attempt and scorecard schemas gain an optional `provenance`
  block, with validators extended accordingly; existing artifacts without
  the block remain valid.
- Aggregate and HTML reports become filterable at user-chosen granularity,
  and the future `yacht serve` dashboard can build its facets on the same
  block instead of inventing its own metadata.
- Cross-version comparisons become expressible and honest: a harness
  upgrade or a tool version bump is visible in the artifacts and flagged
  in mixed aggregates.
- Provenance summarizes facts whose raw sources remain in machine
  evidence and setup results; the duplication is accepted because the
  summary is the queryable surface and the evidence is the audit trail.
