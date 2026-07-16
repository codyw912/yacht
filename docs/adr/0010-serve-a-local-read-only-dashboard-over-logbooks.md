# ADR 0010: Serve a Local Read-Only Dashboard over Logbooks

## Status

Proposed

## Context

YACHT's results surface is per-run: `yacht report` renders one logbook, and
the aggregate command combines repeated runs of one regatta. As runs
accumulate — across tools under test, harnesses, models, and versions —
there is no way to see the collection: which comparisons exist, how verdicts
distribute, or how the same tool performed across harness versions. The
provenance block (ADR 0009) put the facts needed for that view into every
artifact; nothing reads them across runs yet, and the hierarchical
filter-and-group query the ADR promised has no home.

The MVP decision deferred exactly this: reports stayed static, self-contained
HTML, and a local dashboard was named as the future workstream. The design
principles that shaped those reports still apply. Artifacts are the source of
truth, evidence must stay inspectable, and the distribution has one runtime
dependency, which browsing local JSON does not justify changing.

## Decision

We will add `yacht serve`: a local, read-only dashboard over a directory of
logbooks.

- **Seventh command.** `serve` joins the six commands of ADR 0006 as a
  second results surface beside `report`. The bar it clears is the same one
  that shaped that list: it answers a user question ("what do my runs say?")
  rather than exposing a pipeline stage.
- **Read-only over artifacts.** The server renders what scorecards and
  attempt artifacts already contain, resolving each page from disk at
  request time — no database, no ingestion step, no writes. Deleting a
  logbook directory removes it from the dashboard. Invalid artifacts render
  as visibly broken entries, never silently skipped.
- **Standard library only.** The server uses Python's stdlib HTTP machinery,
  binds to localhost by default, and adds no runtime dependency. It is a
  single-user inspection tool, not a deployment target; there is no
  authentication and no remote-exposure support.
- **Server-rendered, no client scripts.** Pages reuse the existing HTML
  report rendering, keeping the no-JS property of ADR-era reports.
  Interactivity — filtering and grouping — is expressed in URL query
  parameters and rendered server-side, so every view is a bookmarkable,
  shareable address.
- **The provenance query layer lands here.** Filtering and grouping by
  provenance dimensions (harness name before exact version, model family
  before exact snapshot, tool and version) is implemented as a plain module
  over artifact JSON, used by the server routes. The CLI can adopt the same
  module later without rework. Views that mix provenance dimensions carry
  the mixed labels of ADR 0009 into the page.
- **Discovery by scanning.** The dashboard takes a root directory (default:
  the existing logbook discovery convention) and finds logbooks by their
  scorecard artifacts. The index groups runs by regatta and course and links
  to per-run pages.

## Consequences

- The CLI grows to seven commands; ADR 0006's completeness guards and
  reference docs are updated to match.
- Provenance filtering gets its first consumer, closing the query half of
  ADR 0009; a later CLI flag reuses the same query module.
- Serving reuses the report renderers, so report improvements benefit both
  surfaces; divergence between `report` output and dashboard pages is a bug.
- The stdlib server is adequate for a local single user and deliberately
  nothing more; if a hosted or multi-user surface is ever wanted, that is a
  new decision with a real web stack, not an extension of this one.
- Pages render from disk on every request: always current, no cache
  invalidation, and slow only if a logbook collection grows far beyond the
  local-use assumption.
