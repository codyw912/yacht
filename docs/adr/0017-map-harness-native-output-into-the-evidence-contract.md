# ADR 0017: Map Harness-Native Output into the Evidence Contract

## Status

Accepted

## Context

ADR 0016 defined `yacht.harness-evidence.v1` as a wire format custom
harnesses emit. The first outside integration (yach) surfaced the
adoption problem with that shape: it asks every harness to add a
yacht-specific output, and established harnesses will not. None of
Pi, Claude Code, or Codex emits yacht's schema — and the yach owner
declined to add it on principle: harnesses should emit standard
formats, not co-invent new ones per evaluator.

Meanwhile every mature harness already has a machine-readable output
mode — Claude Code `--output-format json`, Codex `exec --json`, Pi
`--print --mode json`, yach's native outcome document — carrying the
same facts yacht needs: response text, token usage, tool calls, model.
The de facto standard surface exists; yacht's wire format duplicates
it at the wrong party's expense. The same integration also showed a
subtler contract gap: a harness whose provider reports no usage can
only emit honest zeros, which yacht then stamps `usage_source:
"reported"` — the wire format has no way to say "present but not
provider-reported."

## Decision

We will let harness declarations map fields from the harness's native
JSON output, making the evidence schema YACHT's internal normal form
rather than a format others must adopt.

- **Declared field-mapping.** A `[harnesses.<name>.evidence_map]`
  table maps dotted paths in the harness's native output onto the
  evidence contract's fields:

  ```toml
  [harnesses.yach.evidence_map]
  response = "response.text"
  input_tokens = "usage.input_tokens"
  output_tokens = "usage.output_tokens"
  tool_calls = "tools.calls"          # [{name, count}] or [names]
  model = "model"                     # optional
  cost_usd = "usage.cost.total"       # optional
  usage_reported = "usage.reported"   # optional boolean path
  ```

  Paths are dotted key lookups into the parsed JSON (the same
  transport modes as today: final stdout line, or the evidence file).
  `response`, `input_tokens`, and `output_tokens` mappings are
  required; a mapped path that is missing or has the wrong type in the
  native document fails the attempt loudly — the no-estimates policy
  is unchanged, only the extraction point moves into config.
- **The wire format remains valid, as the identity mapping.** A
  harness that emits `yacht.harness-evidence.v1` directly declares no
  `evidence_map` and everything works as today. The schema keeps its
  role as the normal form all extraction converges to — validated,
  versioned, and used unchanged by everything downstream.
- **Unreported usage becomes expressible.** The optional
  `usage_reported` mapping (and a `usage.reported` boolean in the wire
  format, evidence schema v1.1) propagates into attempt metrics as
  `usage_source: "unreported"` — distinct from `reported` and
  `estimated` — so honest zeros stop masquerading as measurements.
- **Both execution paths.** The mapping applies wherever evidence is
  read: the yacht-run launcher and the generic Harbor agent, which
  carries the mapping in its declaration payload like every other
  field.

## Consequences

- The whole cohort of established harnesses becomes measurable with
  zero harness-side changes — the declaration plus a mapping table is
  the entire integration, which is what "measuring harnesses yacht
  does not ship" was always supposed to mean.
- Adoption cost lands on the right party: the person who wants the
  measurement writes the mapping, not the harness maintainer.
- Mappings are config-authored claims about someone else's output
  format; a harness changing its native JSON breaks the mapping
  loudly (missing mapped path → failed attempt), which is the correct
  failure direction and the reason mapped fields are never defaulted.
- The dotted-path language is deliberately minimal — key traversal
  only, no transforms or arithmetic. Anything the mapping cannot
  express is a case for emitting the wire format natively; the
  escape hatch stays.
- A third `usage_source` value ripples through metrics validation and
  report rendering; aggregates can now exclude or annotate unreported
  usage rather than averaging honest zeros into cost comparisons.
- The evidence documents stored in transcripts remain normal-form, so
  logbooks stay uniform regardless of which harness or mapping
  produced them; the raw native document is preserved alongside for
  audit.
