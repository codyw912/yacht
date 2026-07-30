# ADR 0018: Compare Against Recorded Baselines

## Status

Accepted

## Context

Every yacht comparison today re-runs all of its vessels. That is the
right default for a fresh experiment, but it is the wrong economics for
the most common ongoing question: has anything regressed since the last
known-good run? Teams — especially custom-harness teams tracking their
own agent against their own evals — want to run the candidate once and
compare against a baseline that already exists on disk, not pay tokens
to re-measure a configuration that has not changed. The friction log
from the first outside integration surfaced the degenerate case
(single-vessel smokes require duplicating a vessel); the real feature
behind it is baseline reuse.

Reusing a stored result is only honest when everything that could
explain a delta — other than the treatment — held still between the
baseline run and now. Most tools assume this; yacht can check it. Every
logbook already records what an attempt ran against: the course adapter
block (including the task-content digest for custom evals and the
contest window for LiveCodeBench), harness name and resolved version,
configured and resolved model, and per-task grading outcomes. A
recorded baseline is therefore verifiable, not just loadable.

## Decision

We will let a comparison reference a recorded baseline instead of
re-running it.

- **A baseline reference replaces a vessel.** A comparison may declare
  `baseline = { logbook = "<path>", vessel = "<name>" }` alongside a
  single live vessel. The pipeline loads the stored vessel's grading
  report, per-task outcomes, usage, and provenance from the referenced
  logbook; preflight, attempts, and launch run only for the live
  vessel. Two-live-vessel comparisons are unchanged.
- **Comparability is verified before anything is compared.** The
  referenced logbook's adapter block must match the current config —
  same course kind, dataset, split, task set, and content digest /
  window where the kind defines one — and the baseline vessel's
  recorded harness version and configured model must match what its
  vessel entry in the current config declares. A mismatch refuses the
  run with the differing fields named, the same posture as the
  task-digest check: silently comparing across changed inputs is the
  failure mode this project exists to prevent.
- **Statistics treat recorded and live outcomes alike.** Stored
  per-task outcomes pair with fresh ones for the sign test; Wilson
  intervals, efficiency metrics, and outcome-confound flags apply
  unchanged. Scorecards and reports label the baseline as recorded
  (source logbook and run date shown), so a reader always knows one
  side was not re-run.
- **Repetitions accumulate against the same baseline.** A repeated run
  re-executes only the live vessel; each repetition pairs against the
  recorded baseline's outcomes. This makes the regression-check loop
  cheap enough to run continuously.
- **Time is a recorded confound, not a hidden one.** A matching model
  id does not guarantee an unchanged model behind a provider's API
  weeks later. The baseline's timestamp and resolved-model provenance
  appear in the comparison output, and the report notes the baseline's
  age. Refusing stale baselines is deliberately not automatic — the
  threshold is the user's judgment — but the age is never invisible.

## Consequences

- Regression checking becomes a first-class, token-efficient loop:
  measure the baseline once, then every candidate run costs only the
  candidate. This is the CI shape for harness and skill development,
  and the single-vessel smoke falls out as the trivial case.
- Comparability verification turns the provenance surface into an
  enforcement mechanism: the fields yacht already records become the
  contract that makes cross-run comparison legitimate. Configurations
  that drifted fail loudly with the drift named.
- A recorded baseline is trusted at the artifact level: yacht verifies
  it matches the config, not that it was honestly produced. Within a
  team's own logbooks that is the right trust model; sharing baselines
  across trust boundaries would need the re-grading story from the
  community-database vision and is out of scope here.
- Paired statistics across time inherit the provider-drift caveat
  above; the labeling keeps verdicts honest ("vs recorded baseline
  from <date>") without blocking the workflow.
- The pipeline gains a per-vessel skip path (no preflight/attempts/
  launch for recorded vessels), which the native-rollout branch
  already prefigures; artifact schemas gain a baseline-source block on
  comparisons and scorecards.
