# ADR 0013: Grade Comparison Verdicts by Statistical Evidence

## Status

Accepted

## Context

YACHT's purpose is turning a tool claim into a trustworthy verdict, and
its verdicts currently outrun their evidence. A comparison's headline —
"resolution worse (-1 resolved, -1.000 rate)" — reads identically
whether it summarizes two hundred tasks or one. The 0.4.0 live
validation produced exactly this: a single Terminal-Bench task where one
harness version resolved and the other did not, rendered with the same
confidence as a real regression. Repetition aggregates are honest in
spirit but heuristic in method: a delta is "within run-to-run variance"
when its mean is smaller than its standard deviation, a rule with no
defined error rate, and single runs get a badge instead of an answer.

The problem compounds where YACHT is heading. Community-contributed
results (the long-horizon vision) and cross-run aggregation only mean
something if the statistics underneath them are defensible, and agentic
benchmarks are expensive enough that "just run it more" needs to be a
quantified recommendation, not a shrug. The roadmap has carried
"publication-quality comparisons" since the beginning; the primitives
exist (per-task outcomes, per-run deltas, repetition aggregates), but
nothing computes evidence from them.

One constraint shapes the method choices: YACHT has a single runtime
dependency and stdlib-only internals. Whatever statistics ship must be
implementable in plain Python — no scipy, no numpy.

## Decision

We will grade every comparison verdict by explicit statistical evidence,
computed from the artifacts YACHT already records.

- **Proportions get Wilson intervals.** Each vessel's resolution rate is
  reported with a 95% Wilson score interval over its submitted tasks
  (and, for repetition aggregates, over all tasks across runs). Wilson
  behaves sensibly at the small counts agentic benchmarks actually have,
  and is closed-form arithmetic.
- **Resolution deltas use the paired structure.** Both vessels attempt
  the same tasks, so the delta's evidence lives in the discordant pairs
  — tasks exactly one vessel resolved. An exact sign test (binomial, via
  `math.comb`) on discordant pairs yields the p-value for "these vessels
  differ"; concordant tasks stop diluting or inflating verdicts.
- **Continuous metrics get t-intervals over repetitions.** Token, cost,
  and duration deltas across repeated runs report mean and a 95%
  t-interval (critical values from a small embedded table; normal
  approximation past it), replacing the mean-versus-stdev rule. Single
  runs report the observed value with no interval, labeled as such.
- **Verdicts speak in evidence tiers.** Every comparison headline
  carries one of three grades, derived from the statistics and phrased
  so the weakest tier cannot be mistaken for a finding:
  - *insufficient evidence* — too few discordant pairs for the test to
    reach significance even in the extreme (the n=1 case lands here,
    labeled as an observation, not a verdict);
  - *not distinguishable* — the test ran and the difference is
    consistent with noise (p ≥ 0.05, or the interval spans zero);
  - *evidence of difference* — p < 0.05, or the interval excludes zero,
    reported with the p-value or interval inline.
- **Artifacts carry the numbers, not just the words.** Scorecards and
  aggregates record counts, interval bounds, discordant-pair tallies,
  and p-values in machine-readable form, so external tools can recompute
  or pool them; the text, markdown, HTML, and dashboard surfaces render
  the grade and the numbers together. The existing variance badges are
  replaced, not supplemented.
- **Reports say what would help.** When evidence is insufficient, the
  report states the smallest discordant count at which the test could
  reach significance, turning "run it more" into a concrete suggestion
  without pretending to be a power analysis.

The default confidence level is 95%, fixed rather than configurable in
the first slice; a config knob is cheap later, and a single default
keeps published artifacts comparable.

## Consequences

- The 0.4.0 live-run example renders honestly: one task, one run,
  "insufficient evidence — observation only", with the resolved/
  unresolved split still visible. Nothing about the data changes; the
  claim made from it does.
- Scorecard and aggregate schemas gain a statistics block; the schema
  contract grows but the change is additive, and old artifacts without
  the block still validate and render (without grades).
- Exact tests and closed-form intervals keep the implementation in the
  stdlib at the cost of methodological range: no mixed models, no
  clustered errors, no multiple-comparison correction across many
  simultaneous comparisons. Those are real limitations, acceptable at
  YACHT's current scale and revisitable behind the same artifact fields.
- The sign test conditions on discordant pairs and ignores how often the
  vessels agree; for very high agreement it is conservative. Conservative
  is the correct failure direction for a tool whose purpose is validating
  claims.
- Verdicts get harder to earn. Comparisons that previously read as
  results will read as underpowered — which is the point, and which the
  what-would-help line keeps constructive.
