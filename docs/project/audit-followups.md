# Audit Follow-Ups (July 2026)

A codebase audit after 0.8.0 checked four dimensions: documented claims
against the implementation, statistical correctness, artifact contract
integrity, and the no-estimates posture. This note records what it
found, what has shipped, and what is left.

The statistical and honesty findings are closed. The contract findings
are not, and they are the recommended next slice.

## Closed

Every fix below went test-first; the failing test that captured each
defect is in the suite.

| Defect | Where | Shipped |
| --- | --- | --- |
| Zero-variance intervals graded as findings — two identical runs produced a zero-width 95% CI graded `evidence-of-difference` | `reports/statistics.py` | #273 |
| Runs that produced no result entered aggregate samples as measured zeros, deflating variance | `reports/benchmark_aggregate.py` | #273 |
| Aggregate headline asserted a bare result beside its own "insufficient" evidence table | `reports/benchmark_aggregate.py` | #274 |
| Declared-harness cost silently read as `$0.00` — the mapping path emits `cost.total_usd`, the reader knew only `cost.total` | `reports/task_attempt_scorecard.py` | #275 |
| `tool_call_count` reported deduplicated distinct tools under a name meaning calls | 12 modules | #277 |
| Repetitions never pooled paired evidence, so the documented skill A/B p-value was a hand calculation | `reports/benchmark_aggregate.py` | #278 |
| Documented claims the implementation did not support (sign-test p-value, a cost figure off by 6x, a delivery column the aggregate never emitted, two nonexistent harness names, thirteen stale ADR statuses) | docs | #272 |
| `run-index.json` had no validator; a malformed index crashed `yacht status` with a raw KeyError traceback | `contracts/schemas.py`, `logbook/index.py`, `reports/benchmark_status.py` | #280 |
| `course-handoff.json` validated on write only; four consumers indexed it blind | `courses/handoff.py` + consumers | #280 |
| Six artifacts had schema constants outside `contracts/schemas.py` and no validator (grading collection, repetitions, aggregate incl. `paired_statistics`, terminal-bench job, grading reports); all now validate on write, and the aggregate, grading collection, and grading report readers validate on read | `contracts/schemas.py` + writers/readers | #281 |
| `real-benchmark-eval.json` carried no `schema` key; now versioned as `yacht.real-benchmark-eval.v1` and validated on write | `workflows/real_benchmark_eval.py` | #281 |
| Summaries were not cross-checked against their own detail rows in the task-attempt scorecard and launch result, and `recorded_vessels` escaped the benchmark scorecard's summary cross-checks | `contracts/schemas.py` | #282 |
| No foreign keys between artifacts: the Every Eval Ever export never checked `total_rows`/`evaluation_id`/checksum against the sibling JSONL or the scorecard's comparisons against the handoff, and the recorded-baseline and EEE handoff reads were bare loads | `reports/every_eval_ever.py`, `workflows/baseline.py` | #282 |

Decisions recorded along the way: ADR 0022 (MCP delivery by tool
namespace, approved but **not implemented**) and ADR 0023 (pooling
paired outcomes, implemented in #278).

## Closed: artifact contract integrity

The audit's contract findings shared one shape — artifacts validated
when written and trusted when read — with one structural cause: every
schema constant defined outside `contracts/schemas.py` had no
validator. All six findings are closed (#280, #281, #282): every
persisted artifact schema constant lives in `contracts/schemas.py`
with a validator, writers validate before writing, crash-prone readers
validate on read, summaries are cross-checked against their detail
rows, and the export and recorded-baseline paths verify their
cross-artifact references.

## Closed: ADR 0022, MCP server delivery

Implemented in #283. Each `mcp-server` install step contributes a
delivery expectation from its own target; observed calls match on the
delimited `mcp__<server>__<tool>` namespace, the server is the reported
unit, and the observed tool suffixes travel as `observed_tools`
description through the task-attempt scorecard, the repetition
aggregate, and the HTML delivery table. Harnesses that do not namespace
MCP tools yield no expectation rather than a marker their transcripts
can never match.

## Verified clean

Worth not re-auditing: exception handling (all 153 handlers name
specific types; none bare), fabricated identifiers or timestamps
(none), backward compatibility with pre-0.8.0 logbooks (old artifacts
are a strict subset; every reader tested against a real 26 Jul
logbook), and the statistics primitives themselves — Wilson, the exact
sign test, the t critical values, and the binomial power arithmetic all
match independently coded references.
