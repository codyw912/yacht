# Measuring a Skill Claim

Skills are the fastest-growing way to change what a coding agent can do —
and the least-measured. The typical evidence that a skill "works" is a
pass-rate delta from a handful of runs, no intervals, no significance,
no pinned inputs. This walkthrough runs the experiment properly: the
same pinned agent, on the same task, with and without a skill, repeated
until the evidence can actually support a verdict.

Everything below is a real run of
[`examples/custom-eval-skill-ab-smoke.toml`](../../examples/custom-eval-skill-ab-smoke.toml)
(10 repetitions, Claude Code 2.1.215, claude-haiku-4-5, total cost
$0.38). Your numbers will differ; the shape of the result is the point.

## The experiment

The task
([`examples/custom-evals/convention-task`](../../examples/custom-evals/convention-task))
asks the agent to add a tool module "following the team's tool-module
conventions." The conventions — a `TOOL_NAME` constant, a
`run(args) -> int` entrypoint, self-registration in `registry.txt` —
are documented only in the skill. The task's verifier checks the
conventions mechanically, so the skill's effect shows up as resolution,
not as an impression from reading transcripts.

The config declares the whole comparison:

- Two vessels share one pinned runtime (`harness_version = "2.1.215"`).
  The only difference is rigging: one installs the skill as a real
  Claude Code skill (a `config-file` step writing
  `.claude/skills/team-conventions/SKILL.md` inside the task
  container).
- The course is a `custom-eval` task directory, pinned by content
  digest. The skill content is declared in the config. Nothing floats.
- Install-only preflight proves the agent and the skill install in a
  real task container before any tokens are spent.

## Run it

```sh
docker build -t yacht/harbor-launcher:harbor-0.20.0 containers/harbor-launcher

LOGBOOK=/private/tmp/yacht-skill-ab-$(date +%Y%m%d-%H%M%S)

uv run yacht run examples/custom-eval-skill-ab-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY \
  --repetitions 10

uv run yacht report --logbook "$LOGBOOK"
```

Why 10 repetitions: the paired sign test needs at least 6 discordant
outcomes (runs where exactly one vessel resolved the task) before any
result can be statistically significant. With one task per run, each
repetition contributes at most one discordant pair — 5 repetitions
cannot escape "insufficient evidence" no matter how well the skill
performs.

## Read the verdict

The real run produced:

```
skill-vs-baseline | resolution better (+7 resolved, +0.700 rate) | ...

Aggregate delta evidence (95% CI on per-run deltas):
comparison        | resolved                      | tokens                                | cost
skill-vs-baseline | difference (CI +0.354..+1.046) | not distinguishable (CI -8596..+52092) | not distinguishable (...)
```

- **The claim is supported, and graded.** Baseline resolved 3/10;
  with the skill, 10/10. The rate delta is +0.700 with a 95% CI of
  [+0.354, +1.046] — grade `evidence-of-difference`. All 7 discordant
  runs favored the skill (sign test p = 0.016). That is a conclusion
  the evidence earns.
- **The non-findings are graded too.** The skill's token, cost, and
  duration deltas are all `not distinguishable` — their intervals
  straddle zero — and the report marks them `[outcome-confounded]`
  besides: failed runs typically stop earlier and spend less, so when
  resolution rates differ, raw usage deltas mix the treatment's cost
  with the outcome's cost. The diagnostic split makes it concrete —
  baseline failures averaged 95.6k tokens, baseline successes 124.6k,
  skill successes 126.1k. Success costs what success costs; the skill
  did not make it more expensive.
- **Efficiency is the decision metric.** Cost per resolved task,
  computed from totals with no conditioning: baseline $0.0579,
  with-skill $0.0205. The skill looks ~3% more expensive per run and
  is ~3x cheaper per unit of delivered work. The report's
  "Efficiency by vessel" section carries this number.
- **The baseline's 30% is the realistic part.** The agent sometimes
  infers the registry convention from the existing code. The skill's
  value is turning *sometimes* into *always* — which is exactly what
  the discordant count measures.

## Was the skill actually invoked?

A skill only has an effect if the agent consults it, and outcomes alone
cannot tell "the skill is useless" apart from "the skill never fired"
(ADR 0019). yacht reads the answer from the trial transcripts Harbor
already preserves: each attempt records its observed tool calls (a
Claude Code skill invocation appears as `Skill:<name>`), the
task-attempt scorecard reports the delivery rate per tool — invocations
over attempts, with a Wilson interval, over all attempts and over
completed attempts separately — and the report's decision summary
carries a delivery column:

```
comparison | resolution | ... | delivery
skill-vs-baseline | resolution better (...) | ... | delivered (team-conventions 10/10)
```

A comparison whose treatment skill never fired is labeled
`NOT DELIVERED` — whatever the resolution delta says, it cannot be
attributed to the skill. The two denominators are both worth reading:
a skill that fires in every completed attempt but rarely overall is
telling you that failing to fire and failing to finish travel
together. Attempts with no preserved trajectory evidence are labeled
unmeasured rather than counted either way.

## Why this beats a pass-rate delta

- Provenance pins the causality: identical harness version, model, and
  task digest across all 20 attempts; the vessels differ only in the
  skill. When the delta moves, it is the treatment moving.
- Every attempt leaves re-gradeable artifacts — trials, verifier
  output, transcripts — in the logbook. The result can be audited or
  re-run, not just believed.
- Sub-threshold results are labeled observations, not findings. A
  single flashy run cannot masquerade as evidence.

To measure your own skill: replace the task directory with tasks that
exercise what your skill claims to improve (write the oracle solution
and validate it at zero token cost first — see the
[custom evals reference](../reference/custom-evals.md)), put your skill
content in the rigging step, and pick a repetition count that gives the
sign test a chance.
