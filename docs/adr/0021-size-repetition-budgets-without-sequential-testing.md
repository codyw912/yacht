# ADR 0021: Size Repetition Budgets Without Sequential Testing

## Status

Proposed

## Context

ADR 0013 made verdicts honest and left a gap on purpose. When evidence
is insufficient, reports state the smallest discordant-pair count at
which the sign test could reach significance — six — explicitly
"without pretending to be a power analysis." That answers *how many
discordant pairs*, which is not the question a team with a budget
actually asks: how many repetitions should I pay for before I start?

Agentic repetitions cost real money and hours. The skill A/B
demonstration needed ten repetitions of a single task to reach a
verdict; a twenty-task course at ten repetitions is a different order of
spend. Deciding that after the fact is guesswork, and guessing wrong is
expensive in both directions — too few and the run cannot conclude
anything, too many and the tokens were wasted proving what five would
have shown.

There is a sharper problem hiding in the current behavior. Today every
underpowered run ends with "insufficient evidence" and an implicit
invitation to run more. If a user obliges — runs one more repetition,
re-reads the p-value, repeats until it crosses 0.05 — they are doing
optional stopping, and the reported p-value no longer means what it
says. Under repeated looks the false-positive rate climbs far above the
nominal 5%; with enough looks, a null effect reaches "significance"
almost surely. yacht is currently structured to encourage exactly this,
which is a defect in a tool whose purpose is preventing false claims.

## Decision

We will report repetition budgets as a planning calculation for a fresh
run, and refuse to support extend-and-recheck.

- **Budgets are computed, not shrugged at.** For a comparison, the
  report states how many discordant pairs are needed for the sign test
  to reach 80% power, and — using the observed discordance rate — how
  many repetitions of this course would be expected to produce them.
  The arithmetic is exact binomial power over `math.comb`, staying
  inside ADR 0013's stdlib constraint.
- **The effect size is an assumption, shown as a range.** Power depends
  on how lopsided the discordant pairs truly are, which a small run
  cannot pin down; taking the observed split as truth would produce
  confidently optimistic numbers. Guidance is therefore reported across
  several assumed splits (a clear win, a moderate one, a marginal one),
  so the user chooses the assumption instead of inheriting one.
  Estimates derived from the current run are labeled as estimates, and
  the discordance rate's own uncertainty is stated alongside it.
- **Budgets describe the next run, not this one.** The recommendation
  names a repetition count to commit to in advance and is phrased for a
  fresh run. Reports will not tell a user to add repetitions to a
  finished comparison and look again, because that is the procedure
  whose error rate we cannot defend.
- **Optional stopping is named where it is tempting.** Wherever a
  report says insufficient evidence, it also says plainly that
  repeatedly extending a run and re-testing until it crosses the
  threshold invalidates the p-value. The warning sits next to the
  temptation rather than buried in documentation.
- **Sequential designs are out of scope, deliberately.** Group
  sequential testing with alpha spending, or an SPRT, would make
  interim looks legitimate — with pre-specified boundaries, a stated
  stopping rule, and machinery to enforce it. That is the honest way to
  allow "stop as soon as you know," and it is a larger commitment than
  this slice. Declining it is precisely why the naive version must be
  refused rather than left ambiguous.

## Consequences

- "Run it more" becomes a number a team can put in a budget before
  spending, which was ADR 0013's stated motivation and is the last
  piece of it left undone.
- Some comparisons will report budgets large enough to be discouraging.
  That is information, not a failure: learning that a claim needs forty
  repetitions to demonstrate is worth knowing before paying for ten
  that cannot settle it.
- Guidance is only as good as its assumed effect size, and reporting a
  range makes that visible rather than hiding it behind a single
  number. Users who want a single number must state which assumption
  they are buying.
- Refusing extend-and-recheck will occasionally feel obstructive to
  someone who just wants one more run. The honest alternative — a
  pre-registered sequential design — remains available as future work,
  and this ADR is the record of why it would be needed.
- The guidance is descriptive text plus artifact fields; it changes no
  verdict and no grade. A comparison that is underpowered stays
  underpowered, and nothing here can be mistaken for evidence.
