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

Decisions recorded along the way: ADR 0022 (MCP delivery by tool
namespace, approved but **not implemented**) and ADR 0023 (pooling
paired outcomes, implemented in #278).

## Open: artifact contract integrity

The audit's severe contract findings are untouched. They share one
shape — artifacts are validated when written and trusted when read —
and one structural cause: **every schema constant defined outside
`contracts/schemas.py` has no validator.**

1. **`run-index.json` has no validator at all.** `RUN_INDEX_SCHEMA`
   lives in `logbook/index.py`; nothing validates against it. Its
   reader in `reports/benchmark_status.py` hard-indexes `run_kind`,
   `status`, `regatta`, `course`, and `comparisons`, and the CLI
   catches only `ConfigError`, so a malformed index produces a raw
   traceback from `yacht status`.
2. **`course-handoff.json` is validated on write and never on read.**
   `validate_course_handoff_document` is called from exactly one place
   — the writer. Four consumers load it with a bare JSON read and index
   required keys.
3. **Six artifacts have no validator**, because their schema constants
   live outside the contracts module: `run-index.json`,
   `benchmark-grading-collection.json`,
   `real-benchmark-repetitions.json`, `benchmark-aggregate.json`,
   `terminal-bench-job.json`, and the grading reports.
   `benchmark-aggregate.json` gained `paired_statistics` in #278 with
   nothing validating it.
4. **`real-benchmark-eval.json` carries no `schema` key at all** — the
   run's top-level summary, 37–46 KB, unversioned, so no external
   consumer can dispatch on it.
5. **Summaries are not cross-checked against their own detail rows** in
   the task-attempt scorecard and the launch result (the benchmark
   scorecard does this correctly), and `recorded_vessels` is missing
   from the top-level summary key set.
6. **No foreign keys between artifacts.** Renaming a comparison in a
   scorecard still validates; the Every Eval Ever export's
   `total_rows` and `evaluation_id` are never checked against the
   sibling JSONL.

Suggested order: (1) and (2) first — they are the two that can crash a
reader — then (3) and (4) as one move that pulls the orphan constants
into `contracts/schemas.py`, then (5) and (6).

## Open: ADR 0022, MCP server delivery

Approved and unimplemented. Derives an MCP server's delivery
expectation from its `mcp-server` install step and matches observed
calls on the delimited `mcp__<server>__<tool>` namespace, reporting the
server as the unit and the observed tool suffixes as description. It
was deliberately deferred so correctness work would not be mixed with a
feature.

## Verified clean

Worth not re-auditing: exception handling (all 153 handlers name
specific types; none bare), fabricated identifiers or timestamps
(none), backward compatibility with pre-0.8.0 logbooks (old artifacts
are a strict subset; every reader tested against a real 26 Jul
logbook), and the statistics primitives themselves — Wilson, the exact
sign test, the t critical values, and the binomial power arithmetic all
match independently coded references.
