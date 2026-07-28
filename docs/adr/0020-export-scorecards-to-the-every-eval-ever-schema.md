# ADR 0020: Export Scorecards to the Every Eval Ever Schema

## Status

Proposed

## Context

Every Eval Ever (arXiv 2606.14516; `evaleval/every_eval_ever`) is the
first serious standardization of eval *results* — a versioned JSON
schema (0.2.2 at time of writing) plus a companion instance-level
schema, a community database on Hugging Face spanning tens of thousands
of models, and converters from Inspect AI, HELM, and
lm-evaluation-harness. It is the interchange layer for results in the
same way Harbor is becoming the interchange layer for tasks, and yacht
already bet on that pattern once (ADR 0015).

The fit is unusually good in one specific place. The schema's
`score_details.uncertainty` carries a standard error and a confidence
interval with an explicit `confidence_level` and `method` — and most
sources feeding the community database have nothing to put there,
because they report bare scores. yacht computes Wilson intervals for
every resolution rate as a matter of course (ADR 0013). Exporting is
therefore not a lossy formality; it contributes exactly the field the
ecosystem is worst at populating.

The fit is bad in one specific place too, and pretending otherwise
would be the failure this project exists to prevent. The schema's unit
of record is *(model, benchmark) → score*. yacht's unit of record is a
*paired comparison between two vessels* — a treatment and a control
that differ by a skill, a tool, or a harness version, graded by a sign
test over per-task outcomes. A vessel is a model *configuration*, not a
model. Flattening a comparison into two independent rows loses the
pairing, which is the thing that makes the verdict valid.

## Decision

We will export benchmark scorecards to the Every Eval Ever schema as a
report format, and we will be explicit about what the schema cannot
carry.

- **Export is a rendering, not a migration.** `yacht report --format
  every-eval-ever` writes the aggregate JSON, and the instance-level
  JSONL beside it, from artifacts already in the logbook. yacht's own
  schemas remain the contract and the source of truth (ADR 0012); the
  export is one-way and derived, never round-tripped back into a run.
  No new top-level command — the six-command surface stands (ADR 0006).
- **One row per vessel, with the pairing preserved as context.** Each
  vessel becomes an `evaluation_results` entry scored on its resolution
  rate, with the Wilson interval in
  `score_details.uncertainty.confidence_interval` (`method: "wilson"`,
  `confidence_level: 0.95`). The comparison it belongs to — the other
  vessel, the resolved/rate delta, the paired sign test's p-value and
  evidence grade — travels in that entry's `additional_details`. The
  delta is never itself exported as a score: a treatment effect is not
  a benchmark result, and nothing in the export should let it be read
  as one.
- **The treatment is recorded where the model is not.** A vessel's
  harness and version, rigging, tools, and skill-delivery rates (ADR
  0019) go in `model_info.additional_details` and `generation_config`,
  so two rows sharing a model id are visibly different configurations.
  yacht's provenance block is the source for every one of these fields.
- **Attribution is declared, never inferred.** `source_type` is always
  `evaluation_run` — yacht only ever reports runs it executed. But
  `evaluator_relationship` (first vs third party) and the source
  organization are facts about the publisher that yacht cannot observe;
  they are declared in config, and the export refuses rather than
  guessing. Mislabeling a first-party result as independent is exactly
  the kind of quiet dishonesty the schema exists to prevent.
- **A recorded baseline exports with its own timestamp.** When a
  comparison reuses a stored baseline (ADR 0018), that vessel's entry
  carries the baseline run's `evaluation_timestamp` and its source
  logbook in `additional_details`, not the current run's. The two rows
  of such a comparison were measured weeks apart, and the export must
  say so.
- **Exporting is not publishing.** The command writes files. Uploading
  to the community database is the user's action, taken deliberately
  with their own credentials — yacht never pushes results outward on
  its own.

## Consequences

- yacht results become comparable and reusable across the ecosystem's
  tooling, and the community database gains records that carry
  uncertainty, provenance, and re-gradeable artifact references rather
  than bare numbers. That contrast is also the clearest statement of
  what yacht is for.
- The instance-level export (`interaction_type: "agentic"`, one row per
  task with its outcome and token usage) makes per-task results
  inspectable by consumers who never see a yacht logbook, at the cost
  of a second artifact whose checksum and row count must stay in sync
  with the aggregate.
- Some of what yacht measures has no schema home: comparison verdicts,
  delivery rates, efficiency metrics, outcome-confound flags. Carrying
  them in `additional_details` keeps them available without pretending
  they are standardized. If the schema grows a comparison concept, this
  is the seam that would adopt it.
- Tracking an external schema means version drift: the export pins the
  schema version it targets and validates against it, so a schema bump
  is a deliberate change with a visible diff rather than silent
  divergence.
- The community database's trust and verification story is
  underspecified today. yacht's exports are honest about their own
  provenance, which is all a producer can do; consuming other people's
  records with the same trust yacht places in its own logbooks would
  need the re-grading story from the community-database vision and is
  out of scope here.
