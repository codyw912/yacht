# Adding a Course

This is the contract for contributing a new benchmark course to YACHT. It
is normative: the interfaces, artifact shapes, and pinning rules below are
what the pipeline, schema validation, statistics, and dashboard depend on.
Three real courses implement it today — `swe-bench`, `terminal-bench`, and
`livecodebench` — and each is cited below as a worked example.

## Pick the execution shape first

Everything else follows from one question: **can the rollout be separated
from the task environment?**

- **Yacht-run** (`native_rollout = False`): the agent runs in YACHT's own
  pinned runtime through a harness adapter and produces an artifact (a
  patch, solution code) that a separate native evaluator grades
  afterwards. SWE-bench and LiveCodeBench are this shape.
- **Native rollout** (`native_rollout = True`): the task *is* the
  environment, the agent must act inside it, and the course's native
  harness owns both rollout and verification. Terminal-Bench (through
  Harbor) is this shape; new Harbor-registry datasets should build on the
  existing Harbor course foundation rather than adding an adapter
  (ADR 0012).

## The two adapters

A course registers a pair of frozen dataclasses in
`yacht/courses/registry.py`, one entry each in `_COURSE_ADAPTERS` and
`_EVALUATOR_ADAPTERS`, keyed by the course `kind`. Registration is the
whole integration switch: the config schema accepts the new
`course.adapter.kind` automatically, `course.adapter.harness` validates
against your `supported_harnesses`, and the CLI, handoff, and scorecard
dispatch through the registry. Course-specific logic lives in a
`yacht/courses/<kind>/` package and is imported lazily from the adapter
methods.

### Course adapter (the task side)

| Member | Obligation |
| ------ | ---------- |
| `kind`, `display_name` | The config identifier and the human name. |
| `supported_harnesses` | Execution harness names valid for `course.adapter.harness` (e.g. `docker`, `harbor`, `local`). |
| `native_rollout` | The shape flag; drives the pipeline branch. |
| `expected_outputs()` | Logbook-relative paths for the candidate records and grading report, under `course-handoff/<kind>/`. |
| `task_prompt_instructions(task)` | The submission contract appended to the harness prompt (yacht-run only): what the response must contain, unfenced. |
| `task_with_context(task, adapter)` | Enrich a config task with dataset context (e.g. load the problem statement); identity if tasks are self-contained. |
| `workspace_for_attempt(...)` | Materialize a per-task workspace (e.g. repository checkout); return the shared workspace if none is needed. |
| `write_predictions_from_attempts(...)` | Yacht-run: extract candidate records from completed task attempts. Native rollout: write the rollout plan (task roster plus whatever the launcher needs). |
| `write_attempts_from_native_rollout(...)` | Native rollout only: synthesize task-attempt artifacts from native trial evidence after grading. Yacht-run courses raise. |

### Evaluator adapter (the grading side)

| Member | Obligation |
| ------ | ---------- |
| `grading_schema` | `yacht.<kind>-grading.v1`. |
| `grading(harness)` | The planned-grading block recorded in the course handoff (`delegated_to`, `execution`, `status`). |
| `launcher_command(...)` | The argv the launch stage executes. It receives the handoff adapter block, tasks, candidate path, native report dir, run id, and vessel name — everything must be derivable from those plus artifacts already in the logbook. |
| `native_report_filename(...)` | Where the launcher writes the native report, conventionally `<vessel>.<run_id>.json`. |
| `write_grading_report(...)` | Validate and wrap the native report; implement as a thin call to `write_course_grading_report` in `yacht/courses/grading.py`. |

## The normalized native report

This is the hard contract between your launcher and everything downstream
(scorecard, statistics, reports, dashboard). Whatever your native
evaluator produces, your launcher translates it into a JSON object with:

- `schema_version` (an integer your grading wrapper pins),
- counts: `total_instances`, `submitted_instances`, `completed_instances`,
  `resolved_instances`, `unresolved_instances`, `empty_patch_instances`,
  `error_instances`,
- id lists: `submitted_ids`, `completed_ids`, `incomplete_ids`,
  `resolved_ids`, `unresolved_ids`, `empty_patch_ids`, `error_ids`.

Invariants enforced at grading: every count equals its id list's length;
all lists are subsets of `submitted_ids`; `resolved_ids` and
`unresolved_ids` are subsets of `completed_ids`; `submitted_ids` exactly
matches the candidate records' instance ids; `total_instances` matches the
course handoff. Extra keys are allowed and encouraged for course-specific
evidence (Terminal-Bench embeds trial summaries; LiveCodeBench records its
window and padding counts). Correct per-task ids matter beyond bookkeeping:
the paired statistics of ADR 0013 are computed from them.

Use the shared helpers: `yacht/courses/artifacts.py` for handoff paths and
JSON/JSONL writers, `yacht/courses/attempts.py` for attempt selection,
`yacht/courses/grading.py` for the grading engine. Do not hand-roll a
third copy of any of them.

## Pinning and trust rules

These are non-negotiable; they are what makes a YACHT verdict worth
trusting (ADR 0009, 0012, 0014).

- **Pin the dataset.** A version reference in config must resolve to
  immutable content (a dataset release, a git commit). No floating
  "latest".
- **Pin the evaluator.** Native evaluators run from pinned versions; when
  the evaluator has no package release, a launcher container image built
  from a pinned commit is the pin.
- **Contain untrusted execution.** If grading executes model-generated
  code, it runs inside a launcher container (`containers/<name>/`), never
  on the host. Terminal-Bench and LiveCodeBench both ship one; follow
  their Dockerfiles.
- **Secrets are explicit.** Only declared env-source secrets reach a
  launcher; never ambient environment, never copied auth state.
- **Provenance never guesses.** Anything synthesized into attempts or
  reports resolves from evidence the run produced, or is null.

## The quality bar

A course PR (or slice series) is complete when it has:

1. **Unit tests** with fixtures for the pure parts: prediction/record
   extraction, native-report translation, launcher command construction,
   grading round-trip. Exact values, not shapes.
2. **Live validation at zero or near-zero token cost**, described in the
   PR: an oracle or reference solution, an install-only run, or a
   deliberately wrong submission graded through the real evaluator.
   Terminal-Bench used Harbor's oracle agent and install-only trials;
   LiveCodeBench used a known-wrong solution over a real problem window.
3. **A pinned example config** in `examples/` that a user can run, with
   its prerequisites in the header comment.
4. **A reference page** in `docs/reference/` covering configuration,
   pipeline shape, and caveats, linked from the README.
5. **An ADR** when the course changes the architecture (a new execution
   shape, a new trust boundary). A course that fits an existing shape
   needs no ADR — that is the point of the contract.
6. A changelog entry under the release in progress.

## Worked examples

| Contract element | swe-bench | terminal-bench | livecodebench |
| ---------------- | --------- | -------------- | ------------- |
| Shape | yacht-run | native rollout | yacht-run |
| Dataset pin | HF dataset + split | registry version → git commits | HF release + date window |
| Candidate records | unified-diff patches | task roster | solution code |
| Native evaluator | `swebench` Docker harness | Harbor in `containers/harbor-launcher` | `lcb_runner` in `containers/lcb-runner` |
| External contract absorbed | patch/prediction format | whole-trial containers, agent installation | whole-window output assertion (padding) |
| Attempt evidence | harness-run attempts | synthesized from trials | harness-run attempts |
