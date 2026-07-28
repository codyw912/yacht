# Recorded Baselines: Compare Without Re-Running

A comparison can reference a vessel's results from an earlier logbook
instead of re-running it (ADR 0018). This is the regression-check shape:
measure the baseline once, then every candidate run costs only the
candidate.

```toml
[[vessels]]
name = "control"
model = "claude-sonnet"
runtime = "my-harness"

[[vessels]]
name = "candidate"
model = "claude-sonnet"
runtime = "my-harness"
rigging = ["new-skill"]

[[comparisons]]
name = "regression-check"
vessels = ["candidate"]
baseline = { logbook = "runs/2026-07-20-control", vessel = "control" }
```

With `baseline` set, `vessels` lists exactly one live vessel. The
baseline vessel stays declared under `[[vessels]]` — that declaration is
what its recorded provenance is checked against — and must differ from
the live vessel by name. Relative `logbook` paths resolve against the
config file's directory. Two-live-vessel comparisons are unchanged.

## What runs, what doesn't

Preflight, task attempts, and the benchmark launch run only for the
live vessel. The recorded vessel's grading outcomes, usage, and
provenance are loaded from the referenced logbook. Statistics treat
both sides alike: stored per-task outcomes pair with fresh ones for the
sign test, and Wilson intervals and efficiency metrics apply unchanged.

With `--repetitions`, each repetition re-runs only the live vessel and
pairs against the same recorded baseline.

## Comparability is verified before anything runs

Reusing a stored result is only honest when everything that could
explain a delta — other than the treatment — held still. Before
preflight, the run verifies that the referenced logbook matches the
current config:

- the course adapter block — kind, dataset, split, harness, plus the
  content digest for custom evals and the contest window for
  LiveCodeBench;
- the task set;
- the baseline vessel's recorded configured model, against the model
  its `[[vessels]]` entry declares now;
- the recorded harness version, when the vessel's runtime declares
  `harness_version`;
- the presence of the baseline vessel's grading report.

A mismatch refuses the run with every drifted field named, in
`failed_stage: "baseline-verification"` of the run summary.

## How results are labeled

The recorded vessel appears in the benchmark scorecard with status
`"recorded"` and a `baseline_source` block: the source logbook, run
date, provenance, and usage totals. Reports mark the comparison with
`[recorded baseline from <date>]` so a reader always knows one side was
not re-run.

A matching model id does not guarantee an unchanged model behind a
provider's API weeks later. The baseline's age is always visible;
refusing stale baselines is deliberately left to your judgment.
