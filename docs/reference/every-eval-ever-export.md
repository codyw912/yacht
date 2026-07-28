# Every Eval Ever Export

yacht can export a benchmark logbook to the
[Every Eval Ever](https://github.com/evaleval/every_eval_ever) schema
(ADR 0020) — the community interchange format for eval *results*, in the
same way Harbor is becoming the interchange format for tasks.

```bash
uv run yacht report \
  --logbook /path/to/logbook \
  --format every-eval-ever \
  --output ./eee-export
```

The export writes one aggregate JSON and one instance-level JSONL per
vessel, sharing a filename stem, exactly as the ecosystem's converters
do. It is a rendering of artifacts already in the logbook: yacht's own
schemas remain the source of truth, and nothing is read back in.

## Declare who is publishing

The schema records who ran the eval and how they relate to what they
measured. yacht cannot observe either fact from a run, so they are
declared in config and the export refuses without them:

```toml
[export]
source_organization_name = "Acme Robotics"
evaluator_relationship = "first_party"   # or third_party, collaborative, other
source_organization_url = "https://acme.example"   # optional
source_name = "Acme agent evals"                   # optional, defaults to the regatta name
```

`source_type` is always `evaluation_run` — yacht only ever reports runs
it executed itself, never scraped documentation. Declaring a
first-party result as independent is the kind of quiet mislabeling the
schema exists to prevent, so this one is yours to state.

The block is captured into `course-handoff.json` when the run starts,
which is what the export reads.

## What the export carries

- **Uncertainty, which most sources leave empty.** Each vessel's pass
  rate ships with its Wilson interval in
  `score_details.uncertainty.confidence_interval`, with `method:
  "wilson"` and the confidence level stated.
- **The configuration, not just the model.** Two rows can share a model
  id and differ entirely in scaffold, so the harness and version,
  runtime image, tools, and skill-delivery rates travel in
  `model_info.additional_details`.
- **Per-task outcomes** as instance rows (`interaction_type:
  "agentic"`), referenced from the aggregate with a sha256 checksum and
  row count.
- **The comparison as context.** The vessel it was compared against,
  the resolved and rate deltas, the sign test's p-value, the evidence
  grade, and the treatment-delivery status all travel in
  `additional_details`.

## What the export deliberately does not do

- **A treatment delta is never exported as a score.** The schema's unit
  is (model, benchmark) → score; yacht's is a paired comparison. The
  delta is recorded as context so a reader can see what a vessel was
  measured against, but exporting it as a benchmark result would invite
  exactly the misreading the pairing exists to prevent.
- **No invented counts.** The schema has a `tool_calls_count` field
  meaning how many calls were made; a yacht attempt records the
  *distinct tools observed*, deduplicated by name. Rather than report
  one as the other, the export leaves the field empty and lists the
  observed tools in row metadata. Token usage appears only when the
  harness reported an input/output split.
- **No uploading.** The command writes files. Publishing to the
  community database is your deliberate action, with your credentials.

## Schema version

The export targets a pinned schema version (`0.2.2`) and validates
against it before writing. A schema bump is a deliberate change with a
visible diff, never silent divergence.
