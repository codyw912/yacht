# Changelog

## Unreleased

### MCP installs through capability-providing riggings (ADR 0024)

- A `[tools.<name>]` entry can declare that it provides the `mcp-server`
  install method for a named harness, and the capability gate accepts an
  mcp-server step when the harness supports it natively or a rigged tool
  provides it. pi-mcp-adapter on pi is the first supported provider:
  yacht renders the adapter's `.pi/agent/mcp.json` with `directTools` on
  and the delimited `mcp` tool prefix, so delivery stays measurable.
- MCP delivery expectations now key on the namespace guarantee rather
  than the harness list, and harbor trials preserve pi's JSONL stream as
  tool-call evidence, so stock-versus-extended MCP comparisons extend to
  pi with delivery evidence on the treatment side.
- Harbor job rendering now refuses mcp-server steps for a harness with
  neither native support nor a declared provider (previously they were
  silently passed through to an agent that could not honor them), and
  agent-extension steps on harbor courses are supported for pi with
  npm-pinned targets.

## 0.9.0 - Artifact Contracts and MCP Delivery

YACHT 0.9.0 closes the July audit's contract findings and the last
delivery-measurement gap: every artifact YACHT writes is now validated
on write and on read, summaries must agree with their own detail rows,
artifacts cross-check the artifacts they reference — and MCP servers,
the most-rigged and least-measured treatment, join skills and
extensions as measurable for delivery from the transcripts runs
already preserve.

### Artifact contract integrity

- Artifacts are no longer trusted on read. `run-index.json` gained a
  validator (it had none) and a malformed index surfaces as a clean
  error from `yacht status` instead of a raw traceback;
  `course-handoff.json` is validated by every consumer through a
  shared `load_course_handoff` instead of four duplicated bare JSON
  loads.
- Every persisted artifact schema constant now lives in
  `contracts/schemas.py` with a validator: the grading collection,
  repetition summary, benchmark aggregate (including the
  `paired_statistics` block 0.8.0 added unvalidated), terminal-bench
  job, and the course grading reports. Writers validate before
  writing; the crash-prone readers validate on read. Statistics
  blocks stay optional in the aggregate contract because older
  logbooks predate them and the renderer enriches.
- `real-benchmark-eval.json` — the run's top-level summary — carries
  `schema: yacht.real-benchmark-eval.v1`, so external consumers can
  dispatch on it.
- Summaries are cross-checked against their own detail rows: the
  task-attempt scorecard and launch result counts must equal the sums
  over their vessels, and `recorded_vessels` participates in the
  benchmark scorecard's cross-checks at both levels.
- Artifacts verify the artifacts they reference: the Every Eval Ever
  export checks each aggregate against its sibling instance JSONL
  (row count, per-row `evaluation_id`, checksum) and refuses a
  scorecard whose regatta, course, or comparison names diverge from
  the course handoff; recorded-baseline handoff reads are validated.

### MCP server delivery (ADR 0022)

- An `mcp-server` install step's target alone makes the server
  measurable: it contributes a delivery expectation matching the
  delimited tool namespace (`mcp__<server>__`), with the delimiter
  intact so a server named `fff` never absorbs calls from one named
  `fff2`. Nothing new is configured, and no tool list can go stale.
- The server is the delivery unit — it counts as delivered when any
  of its tools fired — and which tools fired is read back out of the
  namespace suffixes as `observed_tools`, reported per run, unioned
  across repetitions, and shown in the HTML delivery table. In the
  bundled example's live validation this distinguished a repetition
  where the server was connected but unused (not-delivered) from two
  where it fired.
- Harnesses that do not namespace MCP tools yield no expectation and
  report unmeasured rather than guessed at. Precise
  `expected_tool_calls` assertions remain available unchanged.
- `examples/custom-eval-mcp-ab-smoke.toml` and
  `examples/custom-evals/mcp-task` are the live-validated A/B: a
  pinned `@modelcontextprotocol/server-filesystem` against a baseline
  on the same task.

### Testing conventions

- Contract vocabularies are derived from the registry that owns them
  (`COURSE_GRADING_SCHEMAS`, like `COURSE_ADAPTER_KINDS` before it) —
  a hand-kept copy missed the two grading schemas declared only in
  the course registry, and the first live MCP run found it before the
  suite did.
- Every Harbor-rollout course kind's grading writer now roundtrips
  through the registry against its own validator at zero token cost,
  and CONTRIBUTING records the conventions: shared seams are tested
  through every caller, and live token-spending runs are the last
  line of verification, never the first.

## 0.8.0 - Recorded Baselines and Delivery Evidence

YACHT 0.8.0 makes the regression-check loop cheap and the skill claim
checkable: a comparison can reuse a stored baseline instead of paying to
re-measure it, and whether the treatment actually fired is now measured
from the transcripts every run already preserves. Results export to the
ecosystem's interchange schema, and "run it more" becomes a budget.

### Recorded baselines (ADR 0018)

- A comparison may reference a stored result instead of re-running it:
  `baseline = { logbook = "<path>", vessel = "<name>" }` alongside a
  single live vessel. Preflight, attempts, and launch run only for the
  live vessel; the recorded side is rehydrated from the referenced
  logbook. Measure the baseline once, then every candidate run costs
  only the candidate.
- Comparability is verified before anything runs. The referenced
  logbook's adapter block (kind, dataset, split, harness, content
  digest, contest window), task set, recorded configured model, and
  recorded harness version must match the current config; drift refuses
  the run with every differing field named, under `failed_stage:
  "baseline-verification"`.
- Stored per-task outcomes pair with fresh ones for the sign test
  unchanged. Scorecards carry the recorded vessel with a
  `baseline_source` block (source logbook, run date, provenance, usage)
  and reports label the comparison "recorded baseline from &lt;date&gt;",
  so a reader always knows one side was not re-run. `--repetitions`
  re-runs only the live vessel against the same baseline.

### Skill-invocation reliability (ADR 0019)

- Whether a skill fired is now evidence, not inference. Attempts
  synthesized from Harbor trials extract observed tool calls from the
  preserved trajectory — a declared harness's mapped `tool_calls`, else
  the Claude Code session transcript, with skill invocations recorded by
  name (`Skill:<name>`). Attempts with no preserved trajectory are
  labeled unmeasured rather than assumed either way.
- Expected invocations are derived, not configured: `agent-skill` tools
  from the SKILL.md their rigging installs, `agent-extension` tools from
  their declared `expected_tool_calls`.
- The task-attempt scorecard reports delivery rate per tool with Wilson
  intervals, over all measured attempts and over completed attempts
  separately — a gap between the two means failing to fire and failing
  to finish travel together. Comparisons whose treatment never fired are
  labeled `not-delivered`: the resolution delta, whatever it is, cannot
  be attributed to the skill. Repetition aggregates pool invocations
  across runs.

### Every Eval Ever export (ADR 0020)

- `yacht report --format every-eval-ever --output <dir>` writes one
  aggregate JSON and instance-level JSONL per vessel, pinned to schema
  0.2.2. Wilson intervals fill `score_details.uncertainty` — the field
  most contributing sources leave empty.
- Publisher attribution is declared, never inferred: an `[export]` block
  supplies the organization and `evaluator_relationship`, and the export
  refuses rather than guessing. `source_type` is always
  `evaluation_run`.
- The schema's unit is (model, benchmark); yacht's is a paired
  comparison. Each vessel exports as its own document with the pairing —
  compared-against vessel, deltas, sign-test p-value, evidence grade,
  delivery status — as context in `additional_details`. A treatment
  delta is never exported as a score. Recorded baselines export with
  their own measurement date. Exporting writes files; publishing stays
  the user's action.

### Repetition budgets (ADR 0021)

- Reports turn "insufficient evidence" into a number to budget: the
  discordant pairs needed for 80% power and the repetitions expected to
  produce them, across several assumed effect sizes (12 pairs at a 90%
  split, 20 at 80%, 49 at 70%), scaled by the observed discordance rate
  and bracketed by that rate's own interval.
- Budgets size a fresh, pre-committed run. Reports now warn, next to the
  temptation, that adding repetitions to a finished comparison and
  re-testing until it crosses p&lt;0.05 is optional stopping and
  invalidates the p-value. Group-sequential designs are deliberately out
  of scope; exact binomial power keeps the stdlib-only constraint.

### Reports and dashboard

- The HTML report and the dashboard reach parity with the terminal
  report's decision metrics: statistical evidence grades, recorded
  baseline and treatment-delivery badges, tokens- and cost-per-
  resolution efficiency columns, usage source, a skill-delivery table,
  the outcome-confound note, and a per-vessel delivery column on the
  aggregate page. Recorded-baseline usage is charted alongside live
  usage.
- The task-attempt scorecard aggregates per-attempt `usage_source` into
  a vessel-level `usage_sources` list.

## 0.7.0 - Custom Harnesses and Honest Usage

YACHT 0.7.0 opens the harness side to configuration: harnesses YACHT
does not ship are declared in config, measured through a mapped
evidence contract, and run on every course kind — validated end to end
by the first outside integration (yach, a Rust coding harness). Usage
reporting also gets honest about outcome confounding.

### Custom harnesses (ADR 0016, amended by ADR 0017)

- A `[harnesses.<name>]` table declares a harness: prompt passing
  (argument or stdin), evidence transport (stdout or file), and — for
  Harbor-format courses — the in-container `command` (with `{model}`
  substitution) and a pinned `install` (url or path + sha256, verified
  launcher-side and again in-container). Runtimes reference declared
  names exactly like built-ins; install-only preflight covers them.
- Evidence is extracted by declared field-mapping over the harness's
  existing machine-readable output (`evidence_map`, ADR 0017): dotted
  paths onto response, usage, tool calls (with counts), model, and
  cost. `yacht.harness-evidence.v1` remains valid as the identity
  mapping and becomes YACHT's internal normal form. Missing mapped
  fields fail loudly — the custom path never estimates.
- All attempt metrics carry `usage_source` (`reported`, `estimated`,
  or `unreported`): built-in adapters mark their fallback estimates,
  and provider-unreported usage (honest zeros) is labeled instead of
  masquerading as a measurement.
- Agent-prompt preflight is deterministic: launch + declared
  expectations decide the outcome, response-shape notes are
  informational, and content assertions are opt-in via
  `expect_response_contains`.
- A contract page (`docs/reference/custom-harnesses.md`) documents the
  launch semantics, the evidence contract and mapping, provisioning,
  and per-course-kind invocation. First-contact fixes from the live
  integration: container bind mounts absolutize relative logbook
  paths, missing-secret errors name the `--secret` fix, preflight
  summaries surface a one-line failure cause, and file-mode evidence
  on container runtimes is rejected with a clear message.

### Measuring skill claims

- `examples/custom-eval-skill-ab-smoke.toml` and the
  [Measuring a Skill Claim](docs/tutorials/measuring-a-skill-claim.md)
  walkthrough: the same pinned Claude Code with and without a skill on
  a convention task, repeated to accumulate discordant outcomes. The
  bundled real run: baseline resolved 3/10, with-skill 10/10, and all
  seven discordant repetitions favored the skill, with token and cost
  deltas honestly not distinguishable.
- Usage deltas are flagged `[outcome-confounded]` whenever resolution
  rates differ (failed runs stop earlier and spend less), reports gain
  "Efficiency by vessel" (tokens and cost per resolved task — the
  decision metric) and a usage-by-run-outcome diagnostic. In the real
  skill A/B, a skill that cost ~18% more per run is ~2.8x cheaper per
  resolved task.

### Project

- The custom-evals reference documents running generated evals
  (Harbor-format tasks from eval-generation tooling) directly under
  the `custom-eval` course.
- Recorded-baseline comparisons are proposed in ADR 0018 (not yet
  implemented).

## 0.6.0 - Custom Evals and Full Evaluator Containerization

YACHT 0.6.0 turns the `custom-eval` kind into a real user-authored eval
system and moves the last native evaluator off the host: every grading
path now runs in a pinned launcher container.

### Custom evals (ADR 0015)

- The `custom-eval` course now runs evals you write yourself: a local
  directory of Harbor-format tasks (instruction, environment
  Dockerfile, verifier) executed through the same pinned launcher,
  yacht-owned agents, rigging, and install-only preflight as the
  registry Harbor courses. Tools that generate evals in Harbor format
  plug in directly; YACHT stays the measurement side.
- The content hash is the pin: the course handoff records a sha256
  digest over the task directory's relative paths and file bytes, every
  pipeline artifact carries it, and the harness recomputes and verifies
  it before launching — tasks edited between planning and launch fail
  loudly instead of silently measuring different content. Runs are
  comparable when their digests match.
- Harbor trial directories — including the verifier's own trajectory —
  are preserved in the logbook so reward-hacked verifiers can be
  audited, not just scored.
- The previous internal mock `custom-eval` kind, its local harness, and
  the `local` course harness are removed; the name now means the real
  course (`harness = "harbor"`, `dataset` = the task directory path,
  `split` = a user-chosen revision label).
- Added a working example task (`examples/custom-evals/hello-task`),
  the `examples/custom-eval-claude-code-versions-smoke.toml` regatta,
  and a Custom Evals reference page. Validated live end to end,
  including a real token-spending comparison run and zero-token oracle
  and install-only runs against the example task.

### SWE-bench grading launcher containerization

- SWE-bench grading runs in the pinned `containers/swebench-runner`
  image (`swebench==4.1.0` fixed at image build), driving per-instance
  evaluation containers through the mounted Docker socket — the
  launcher-image pattern from ADR 0012 now covers all three native
  evaluators, and no grading executes on the host.
- The `--python-executable` escape hatch and the floating
  `uv run --with swebench` resolution are removed; the image pin is the
  resolution. `yacht doctor` now verifies the runner image is present.
- Harness logs land inside the logbook's native-report directory
  instead of scattering on the host.

### Project

- Task-directory mounts into the launcher container are read-write:
  read-only binds of macOS directories intermittently surface as
  missing inside containers under OrbStack's virtiofs, and the content
  digest is what guards task integrity.

## 0.5.0 - Statistical Verdicts, LiveCodeBench, and Aider Polyglot

YACHT 0.5.0 makes comparison verdicts statistically honest, adds two
benchmark courses — LiveCodeBench through its official evaluator and
Aider Polyglot on the Harbor foundation — and publishes the contract for
contributing new courses.

### Statistical rigor (ADR 0013)

- Comparison scorecards now carry a `statistics` block per comparison:
  Wilson score intervals on resolution rates and an exact paired sign
  test over discordant tasks, all stdlib-only.
- Resolution verdicts are graded by evidence: `insufficient-evidence`
  (fewer discordant tasks than the significance threshold — an
  observation, not a conclusion), `not-distinguishable` (p >= 0.05), or
  `evidence-of-difference` (p < 0.05). Reports append the grade to the
  decision line instead of presenting raw deltas as findings.
- Repetition aggregates replace the old variance heuristics with
  t-based 95% confidence intervals on per-run deltas, graded the same
  way; HTML reports badge the grade and label single runs as
  observation-only.

### LiveCodeBench course (ADR 0014)

- Added the `livecodebench` course: YACHT runs the rollout (competitive
  programming problems fetched with full context from the pinned
  dataset), and grading is delegated to the official LiveCodeBench
  evaluator, pinned by commit in a dedicated launcher image
  (`containers/lcb-runner`) so untrusted generated code executes only in
  a container.
- Course configs declare the contest-date window (`start_date` /
  `end_date`) that selects the problem set; unattempted window problems
  are padded into the evaluator input as required by the harness and
  reported distinctly from real submissions. The window is carried
  through every pipeline artifact and validated at each stage.
- Added `examples/container-claude-code-livecodebench-smoke.toml`
  (haiku vs sonnet on two problems) and a LiveCodeBench reference page.
  Validated live end to end with a real token-spending comparison run.

### Aider Polyglot course

- Registered `aider-polyglot` (225 Exercism tasks across six languages)
  on the Harbor course foundation from 0.4.0 — same yacht-owned agents,
  pinned launcher, rigging, and install-only preflight; only the
  dataset pin and grading schema differ. Added
  `examples/aider-polyglot-claude-code-versions-smoke.toml`.

### Project

- Documented the course contract (`docs/reference/adding-a-course.md`):
  the decision tree between yacht-run and native-rollout shapes, the
  adapter surfaces to implement, the normalized native report
  invariants, and the pinning and trust rules a new course must satisfy.
  CONTRIBUTING.md now leads with it.
- Course adapter blocks are rebuilt from one shared helper across all
  pipeline artifacts, fixing mid-run validation failures where
  LiveCodeBench window fields were dropped between stages.

## 0.4.0 - Terminal-Bench and the Harbor Course Foundation

YACHT 0.4.0 adds the second real benchmark course — Terminal-Bench 2.0 —
and, underneath it, a general foundation for running Harbor-format courses
with YACHT-owned agents in a hermetic launcher (ADR 0011, ADR 0012).

### Terminal-Bench course

- Added the `terminal-bench` course: rollout and verification are
  delegated to Terminal-Bench's official Harbor harness, which builds each
  task's own container, installs the pinned agent inside it, runs the
  agent, and runs the task's tests. Courses can now declare native
  rollout, and the pipeline skips YACHT-side task attempts for them.
- Harbor's per-trial results translate into the normalized grading
  reports the scorecard consumes (verifier reward to resolved/unresolved,
  exceptions to errors, missing trials to incomplete), and task-attempt
  artifacts are synthesized from trial evidence so Terminal-Bench runs
  carry the same usage and provenance surface as harness-run attempts —
  harness version and model resolved from what Harbor actually installed
  and ran, null when absent, never guessed.
- Added `examples/terminal-bench-claude-code-versions-smoke.toml`
  (pinned Claude Code 2.1.211 vs 2.1.215 on one task) and a
  Terminal-Bench reference page. Validated live end to end, including a
  real token-spending comparison run.

### Yacht-owned agents and the pinned launcher (ADR 0012)

- Vessels on Harbor courses run through YACHT's own agent classes, baked
  into a pinned launcher image (`containers/harbor-launcher`): the pinned
  harness is installed and YACHT's typed rigging steps are applied inside
  the task container — pinned npm `package` installs, `config-file`
  content behind a traversal guard, and stdio `mcp-server` entries.
  Unpinned packages and inexpressible methods are rejected before launch,
  and trial evidence names the agent implementation.
- The orchestrator is hermetic: Harbor and its dependencies resolve at
  image build time, and the launcher container sees only the mounted
  trial directory, the Docker socket for sibling task containers, and
  explicitly declared secret environment variables.
- Added the `harbor` runtime backend: recipes declare the launcher
  image, harness, and a required pinned `harness_version` — no
  ceremonial commands or flakes — and validation enforces course/backend
  agreement in both directions. No rigging ever executes on the host for
  these vessels.
- Added the `install-only` preflight check: Harbor's install-only trial
  mode proves agent-plus-rigging installation in a real task container
  before tokens are spent, passing only when the trial records the
  installed agent version.

### Project

- Course-agnostic grading, artifact, and attempt helpers extracted from
  the SWE-bench package into shared course modules.
- Recorded the Terminal-Bench decision (ADR 0011) and the Harbor-course
  architecture with its independence constraints (ADR 0012): YACHT
  schemas remain the contract, official native harnesses remain grading
  truth, and the roadmap keeps a maintained non-Harbor course.
- The dashboard skips unreadable directories during logbook discovery
  instead of failing the whole scan.

## 0.3.0 - Tool-Claim Validation, Provenance, and the Dashboard

YACHT 0.3.0 delivers the tool-claim validation workstream: a second real
harness, executable MCP-server rigging, human-friendly HTML verdicts, run
provenance for granular aggregation, and a local dashboard over logbooks.

### Claude Code harness

- Added the `claude-code` harness adapter alongside `pi` (ADR 0008): task
  attempts run headless `claude --print --output-format stream-json`, tool
  calls, tokens, cost, and duration are parsed from the stream into the same
  task-attempt fields Pi populates, and an exit-0 run without a valid result
  message fails loudly instead of recording estimated usage.
- Added the pinned `containers/claude-code-runtime` image
  (`@anthropic-ai/claude-code@2.1.211` on Node 22, isolated `yacht` user).
- Permission bypass (`--dangerously-skip-permissions`) is refused on
  non-container backends; agent-prompt preflight runs without it.

### Rigging for tools under test

- `config-file` installs write declared content into the trial home behind a
  traversal guard, and `package` installs execute pinned npm targets through
  the runtime, with every setup action recorded as evidence in task-attempt
  artifacts.
- `mcp-server` installs are executable through a harness adapter hook that
  renders declared servers into the harness's own config format inside the
  trial home (Claude Code: user-scope `mcpServers`); harnesses without a
  renderer still block the method before tokens are spent.
- Added `examples/container-claude-code-mcp-real-task-smoke.toml` (pinned
  tool version, offline MCP server start, live-tool preflight) and the
  "Validating a Tool Claim" tutorial documenting the full loop.
- Vessels whose runtime and riggings declare no preflight checks are
  rejected with an actionable error instead of passing an empty preflight.

### HTML reports

- `yacht report --format html` writes a single self-contained file (no
  scripts, no external assets) with a verdict banner, small-sample and
  run-variance badges, per-vessel outcomes and usage, tool-call evidence
  tables, and per-task results; repetition parent logbooks render the
  aggregate with variance-aware verdicts.

### Run provenance (ADR 0009)

- Every task attempt records a `provenance` block resolved only from
  evidence the run produces: harness name and version from the pinned image
  tag, configured versus API-reported model, runtime backend and image,
  pinned tool versions, and the yacht version. Unresolvable values are null,
  never guessed.
- Scorecards and benchmark aggregates collapse provenance upward; any
  dimension where runs disagree becomes null and is labeled under `mixed`,
  with a warning badge and provenance tables in aggregate reports, so
  blended results are never presented as homogeneous.

### Dashboard (ADR 0010)

- Added `yacht serve`, the seventh command: a stdlib-only, localhost,
  read-only dashboard that rescans a root of logbooks and renders from
  artifacts on every request. The index groups runs by regatta and course
  with broken logbooks shown visibly; per-run pages reuse the HTML report
  renderer verbatim.
- The `/vessels` view filters and groups every vessel run by hierarchical
  provenance facets through bookmarkable URL query parameters — a harness
  filter matches every version while `harness.version` matches exactly —
  with mixed-provenance records confined to a labeled unknown bucket.

## 0.2.0 - First Published Release

The first release distributed on PyPI as `yacht-eval` (the import package and
CLI stay `yacht`). YACHT 0.2.0 consolidates the command surface, hardens the
first-run path, and generalizes the evaluation pipeline that 0.1.0 proved.

### CLI

- Consolidated the user-facing CLI to six commands: `doctor`, `run`,
  `validate`, `status`, `report`, and the `internals` group holding the
  pipeline stage commands for debugging and incremental re-runs (ADR 0006).
- Added `yacht doctor` for host prerequisite checks: Python, uv, Git, the
  Docker CLI and daemon, logbook writability, the native SWE-bench harness,
  and config-aware runtime image and secret checks, each with an actionable
  hint.
- Unified `yacht run` to execute the full pipeline and detect smoke versus
  benchmark courses from the config, with `--repetitions` for repeated
  benchmark runs aggregated under one parent logbook.
- Unified `yacht status` and `yacht report` to detect the run type through
  the logbook run index and default to `./logbook`, then the most recent
  yacht logbook.
- Runbook artifacts are written automatically at the start of each run, and
  every next-step hint emitted into artifacts names a runnable command.

### Evaluation pipeline

- Required secrets are validated before task context loading and workspace
  materialization, so misconfigured runs fail before network work or tokens
  are spent.
- SWE-bench dataset records are cached per process, keyed by dataset and
  split, so multi-task and multi-vessel runs load each split once.
- Task IDs, vessel names, and comparison names from config are validated as
  path-safe before they are interpolated into logbook paths.
- Repeated benchmark runs produce per-run rows, aggregate statistics for
  resolution rate, tokens, cost, duration, and tool calls, and an automatic
  markdown report on the parent logbook.
- Typed rigging install steps describe agent extensions, MCP servers,
  packages, binaries, container images, preinstalled tools, and custom
  commands; unsupported capabilities are blocked with explicit
  `runtime-capability` preflight evidence before setup commands run.
- The agent harness is selected from configured runtime surface metadata
  instead of assuming Pi, and artifacts report which harness ran each vessel.
- Fixed agent-prompt preflight JSON extraction when agents wrap the required
  JSON object in a Markdown fence, and fixed smoke readiness resolution for
  relative logbook paths.

### Project

- The unit suite is hermetic (no network) and runs in seconds; CI enforces
  ruff lint and formatting and reports coverage.
- Production input validation uses explicit project errors instead of
  asserts.
- Recorded architecture decisions for the six-command CLI (ADR 0006) and the
  `yacht-eval` distribution name (ADR 0007).

## 0.1.0 - First Usable Benchmark Smoke

- Added a real end-to-end SWE-bench Lite smoke path for containerized Pi
  baseline vs containerized Pi+fff.
- Added runtime and rigging preflight evidence before task tokens are spent.
- Added SWE-bench task context loading, per-task repository checkout, agent
  task attempts, candidate patch extraction, native SWE-bench Docker grading,
  and normalized benchmark scorecards.
- Added a one-task smoke config and a two-task small smoke config:
  `examples/container-pi-fff-real-benchmark-smoke.toml` and
  `examples/container-pi-fff-real-benchmark-small.toml`.
- Added benchmark status and report output with notable deltas, per-vessel
  usage, per-task usage, per-task outcomes, and artifact paths.
- Added runbook generation for real benchmark runs so users can inspect the
  exact commands and expected artifacts before spending provider tokens.
