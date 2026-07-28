# ADR 0019: Measure Skill-Invocation Reliability from Preserved Transcripts

## Status

Proposed

## Context

A skill A/B measures whether installing a skill changes outcomes. But a
skill only has an effect if the agent actually consults it, and
invocation is the least-verified link in the chain. Today a null result
is ambiguous — the skill may be useless, or it may never have fired —
and a positive result may be luck that had nothing to do with the
skill. Teams shipping skills ask a sharper question than "did outcomes
move": does the skill fire when it should, every time, across
repetitions? That reliability is itself the claim to validate, and
nothing in yacht measures it.

The evidence already exists on disk and is already thrown away. Harbor
trials preserve the agent's full session transcript (for Claude Code, a
`Skill` tool use with the skill's name appears in the session JSONL
under the trial directory), but attempts synthesized from trials
hard-code an empty `tool_calls` list, so invocation evidence never
reaches an artifact. Meanwhile the configuration already declares
intent: tools carry `expected_tool_calls` and a kind (`agent-skill`,
`agent-extension`), riggings tie tools to vessels, and the smoke path
already extracts observed tool calls from Claude Code stream-json
output. The gap is between the benchmark path's preserved trajectories
and the attempt evidence contract.

## Decision

We will extract observed tool invocations from preserved harness-native
transcripts into attempt evidence, and grade treatment delivery as a
first-class part of comparison verdicts.

- **Observed invocations become attempt evidence.** Attempts
  synthesized from native trials parse the preserved transcript and
  populate the attempt's observed tool calls, per harness: Claude Code
  from its session JSONL (skill invocations recorded by skill name),
  declared harnesses through an `evidence_map` key in the posture of
  ADR 0017. A harness that surfaces no trajectory yields no observed
  calls and the absence is recorded as unmeasured — never inferred
  from the outcome.
- **What counts as an invocation is derived, not configured, where it
  can be.** An `agent-skill` tool matches automatically by its skill
  name — the invocation event carries it, so the common case needs no
  declaration. An `agent-extension` tool matches its declared
  `expected_tool_calls`, the vocabulary preflight already uses.
  MCP servers are out of scope for this slice and follow later.
- **Invocation reliability is reported per vessel and tool.** For each
  rigging-installed tool, the scorecard reports invocations over all
  attempts — the delivery rate — with the same Wilson interval
  treatment as resolution rates, alongside the rate over completed
  attempts. Both denominators are load-bearing: a gap between them is
  itself evidence, because a failure to invoke the skill may be the
  cause of a failure to complete. Across repetitions this makes "the
  skill fires in 9/10 runs" a measured, evidence-backed claim, and
  skill-triggering flakiness a quantity rather than an anecdote.
- **Verdicts state whether the treatment was delivered.** A comparison
  whose treatment-arm tool was never observed to fire is labeled
  not-delivered: the resolution delta, whatever it is, cannot be
  attributed to the skill. Like outcome-confound flags, this labels
  the verdict rather than blocking the run — and when invocation was
  unmeasured, the label says that instead, which is a different and
  honestly weaker statement.
- **No invocation-conditioned causal claims.** Resolution split by
  invoked-versus-not conditions on a post-treatment variable and is
  not a causal comparison. Reports may show the split descriptively,
  clearly labeled as observational; the graded verdict never uses it.

## Consequences

- The skill A/B walkthrough gains the missing half of its story:
  delivery rate alongside outcome delta, and an honest label when a
  "skill effect" was measured in runs where the skill never fired.
- Regression checks against recorded baselines (ADR 0018) extend
  naturally to reliability: a skill update can be checked for "still
  fires as often" as cheaply as "still resolves as often".
- Extraction is harness-specific by design. Claude Code is covered
  natively; custom harnesses opt in through the declared-harness
  evidence contract; anything else reports unmeasured. This keeps the
  provenance posture — record what the evidence shows, never guess —
  at the cost of uneven coverage across harnesses.
- Transcript parsing becomes load-bearing for a graded label, so the
  parsers inherit the same schema-validation discipline as grading
  reports: unrecognized transcript formats degrade to unmeasured, not
  to wrong counts.
- Attempt artifacts grow an observed-invocations surface that the
  dashboard and reports can drill into (which tools fired, per task),
  independent of any skill claim.
