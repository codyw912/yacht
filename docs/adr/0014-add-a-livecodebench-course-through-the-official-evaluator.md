# ADR 0014: Add a LiveCodeBench Course Through the Official Evaluator

## Status

Proposed

## Context

ADR 0012 committed YACHT to keeping at least one major course integrated
outside the Harbor ecosystem, so the course/evaluator seam stays proven
against contracts we do not choose. LiveCodeBench is the named target: a
contamination-aware competitive-programming benchmark whose problems are
dated by contest, letting evaluations restrict themselves to problems
published after a model's training cutoff.

Its official harness sets the contract. There is no PyPI package — the
evaluator installs from the git repository — and evaluation runs
`lcb_runner.runner.custom_evaluator`, which accepts externally produced
generations as `{question_id, code_list}` records, loads the pinned
dataset release (`release_v1` through `release_v6` on Hugging Face,
optionally filtered to a contest-date window), executes the generated
code against public and private test cases with per-test timeouts, and
asserts that the outputs file covers the entire loaded benchmark — no
arbitrary-subset selection. Grading therefore means running untrusted
model-generated code, which the official tool does with host
multiprocessing.

The shape is SWE-bench's, not Terminal-Bench's: the agent produces an
artifact (solution code) that a separate native evaluator grades after
the fact. Rollout belongs to YACHT's own harness adapters and pinned
runtime images — deliberately exercising the yacht-run path that the
Harbor foundation must not atrophy.

## Decision

We will add a `livecodebench` course: YACHT-run attempts graded by the
official LiveCodeBench evaluator in a pinned launcher container.

- **Attempts run on YACHT's harnesses.** Task context loads the pinned
  dataset release from Hugging Face (the same machinery as SWE-bench
  task context), the problem statement and starter code go into the
  prompt, and the harness responds with a JSON object carrying the
  solution code — the same response contract style as SWE-bench's
  `model_patch`, with the same fenced-output tolerance.
- **Task selection follows the benchmark's own axis.** The course
  selects problems by contest-date window, mapped one-to-one onto the
  official loader's `--start_date`/`--end_date` filter, with optional
  explicit question ids inside the window. Windows are how the benchmark
  expresses contamination control, so the selection mechanism doubles as
  provenance: the window is recorded in the adapter configuration.
- **The whole-window assertion is satisfied by padding.** The official
  evaluator requires an output for every problem in the loaded window.
  Problems inside the window that YACHT did not attempt are submitted
  with empty code, marked as padding in the candidate records, and
  excluded from YACHT's submitted set — they exist to satisfy the
  external contract, never to count in results.
- **The evaluator runs in a pinned launcher image.** A YACHT-built
  container bakes in the LiveCodeBench repository at a pinned commit
  with its locked dependencies, following the harbor-launcher pattern
  (ADR 0012). Containerization is not optional here: grading executes
  untrusted generated code, and the launcher container is where that
  happens — never the host. The evaluator's per-test timeouts and
  process pool run inside it unchanged.
- **Grading translates per-instance results.** The launcher wrapper
  reads the official per-question evaluation output, takes pass@1 over a
  single sample per problem (more samples are a later, additive knob),
  and writes the normalized grading report over YACHT's submitted ids —
  resolved when the official evaluator passed the code, with padding
  entries dropped. The scorecard, statistics (ADR 0013), reports, and
  dashboard consume it unchanged.

## Consequences

- The course/evaluator seam absorbs a genuinely external contract — a
  git-only distribution, a whole-benchmark output assertion, date-window
  subsetting — validating that the interfaces are not quietly shaped
  around Harbor or SWE-bench.
- YACHT's harness adapters and runtime images get a second real course,
  keeping the yacht-run rollout path exercised alongside native
  rollouts, per the ADR 0012 discipline.
- The launcher-container principle now covers two of three native
  evaluators; the SWE-bench grading launcher remains the last host
  process, and moving it is unchanged in priority but now has two
  precedents.
- Pinning is by git commit rather than package version; the launcher
  image build is the pin, and provenance records it. Upstream breakage
  surfaces at image rebuild, never mid-run.
- Padding makes small runs pay the evaluator's cost for empty entries in
  the window; tight windows keep this negligible, and the wrapper
  reports padding counts so the cost is visible rather than silent.
- Single-language (Python) and single-sample pass@1 bound what verdicts
  can claim initially; both are recorded limitations, not hidden ones.
