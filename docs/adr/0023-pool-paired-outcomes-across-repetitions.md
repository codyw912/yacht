# ADR 0023: Pool Paired Outcomes Across Repetitions

## Status

Proposed

## Context

ADR 0013 established that resolution deltas use the paired structure:
both vessels attempt the same tasks, so the evidence lives in the
discordant pairs and an exact sign test grades them. The repetition
aggregate never implemented that rule. It grades per-run deltas with a
t-interval instead, and `paired_resolution_statistics` is called from
exactly one place — the single-logbook scorecard.

The consequences are not subtle. A ten-repetition run of a one-task
course produces ten independent single-task sign tests, each pinned at
`insufficient-evidence` by construction, because one task cannot supply
the six discordant pairs the test needs. The discordant outcomes exist
in the per-run artifacts and nothing combines them. Meanwhile the
t-interval is applied to a bounded discrete quantity — for a one-task
course each run's rate delta is drawn from {−1, 0, +1} — and its actual
type-I error rate, enumerated exactly against a nominal 5%, is 0.50 at
two runs and 0.125 at four and at seven. The method has no defined
error rate on this data.

Three things depend on the gap being closed. The bundled skill A/B has
been documented for two releases with a pooled p-value that YACHT does
not compute; a human worked it out from the per-run scorecards. The
repetition budgets from ADR 0021 convert required discordant pairs into
a repetition count, which is only meaningful if repetitions pool. And
the whole premise of paying for repetitions is that evidence
accumulates.

Pooling raises a question that must be answered rather than assumed.
Repeated attempts at the *same* task are not independent draws: task
difficulty is a fixed property, and a task no agent can solve
contributes concordant pairs forever while a coin-flip task contributes
discordant ones. Treating every (task, repetition) pair as exchangeable
overstates the effective sample size when tasks differ in difficulty —
the clustering problem. Wilson intervals over pooled attempts have the
same defect, which is why ADR 0013's parenthetical about pooling rates
across runs was never safe to implement literally.

## Decision

We will pool discordant outcomes across repetitions and grade them with
the sign test, and we will state what the pooling assumes.

- **The unit of pairing is the task attempt, not the task.** Each
  repetition of each shared task contributes one pair: concordant when
  both vessels resolved it or neither did, discordant toward whichever
  vessel resolved it alone. The aggregate sums these across runs and
  grades the total with the same exact sign test used for a single
  logbook, so ten repetitions of one task can reach a verdict that one
  repetition of one task cannot.
- **The sign test's null survives clustering; the effective sample size
  does not.** Under the null that the vessels are equivalent, each
  discordant pair favors either side with probability one half whatever
  the task's difficulty, because both vessels faced that same task on
  that same repetition. Clustering does not bias the test toward a
  false positive; it inflates the *precision* implied by a given pair
  count when a few easy-to-flip tasks supply most of the discordance.
  Aggregates therefore report how the discordant pairs are distributed
  across tasks alongside the p-value, so a verdict resting on one
  flapping task is visible as such rather than reading like a verdict
  resting on twenty tasks.
- **Pooled rates do not get a Wilson interval.** Repeated attempts at
  the same task are not independent Bernoulli trials, so a Wilson
  interval over pooled attempts would claim precision the design does
  not support. Per-run rates keep their intervals; the pooled figure is
  reported as an observed proportion with its run count, uninterval-ed.
  ADR 0013's parenthetical to the contrary is superseded here.
- **The t-interval stops grading resolution deltas.** It remains
  appropriate for continuous per-run quantities — tokens, cost,
  duration — where run-level means are the natural unit. For
  resolution, the paired test replaces it, and the impossible interval
  bounds that a normal-theory method produces on a bounded quantity
  disappear with it.
- **Single-run aggregates say what they are.** One repetition pools to
  one run's worth of pairs and will usually grade insufficient. That is
  the same answer the per-run scorecard gives, arrived at the same way,
  rather than a different method reaching a more confident conclusion
  from the same data.

## Consequences

- The documented skill A/B result becomes something YACHT computes
  rather than something a human computed about YACHT: seven discordant
  repetitions all favoring the skill, p = 0.016, graded
  evidence-of-difference by the same code path a single logbook uses.
- Repetition budgets become actionable. A budget that says "twenty
  discordant pairs at an assumed 80% split" now describes a quantity
  the aggregate will actually accumulate and test.
- Verdicts on repeated runs get harder to earn in the cases where they
  should be. Comparisons that reached `evidence-of-difference` through
  a degenerate or ill-fitted t-interval will report insufficient
  evidence until the discordant pairs are genuinely there.
- Reporting the per-task distribution of discordant pairs adds a
  surface, and it is the honest price of pooling: without it, a pooled
  p-value cannot be distinguished from one earned across many tasks.
- Clustering is acknowledged, not corrected. A mixed-effects or
  cluster-robust treatment would model task-level variance directly and
  is out of scope for a stdlib-only implementation; naming the
  limitation and showing the distribution is what this slice offers
  instead.
