# YACHT

Yet Another Coding Harness Testbed.

YACHT is an evaluation control plane for agentic coding systems. It runs the
same coding course across different agents, models, tools, prompts, memory
systems, and runtime environments, then records the evidence needed to decide
whether a change actually helped.

The goal is not only to produce benchmark scores. A useful YACHT run should
also answer:

- Did the setup solve the task?
- Was the runtime available, isolated, and configured as claimed?
- Which tools were actually used?
- How many tokens did the run spend?
- What did it cost?
- How long did it take?
- Which artifacts prove the result?

YACHT is designed as open-source infrastructure for reproducible, inspectable
coding-agent evaluation.

## Current Status

YACHT runs real end-to-end benchmark comparisons:

- harness adapters for containerized Pi, Claude Code, OMP, and Codex,
  plus harnesses YACHT does not ship: declared in config and measured
  through a mapped evidence contract over their own machine-readable output
- rigging for tools under test: agent extensions, skills, config files,
  pinned npm packages, and MCP servers rendered into the harness's own
  configuration
- explicit secret injection, runtime and rigging preflight before tokens are
  spent
- five course kinds: SWE-bench Lite (per-task checkout, candidate patch
  extraction, native Docker grading), Terminal-Bench 2.0 and Aider Polyglot
  on the Harbor foundation, LiveCodeBench through the official evaluator
  with contest-date windows recorded as contamination provenance, and
  `custom-eval` for evals you write yourself as Harbor-format task
  directories, pinned by a content digest
- comparison verdicts graded by statistical evidence: Wilson intervals,
  paired sign tests, and t-intervals over repeated runs, with
  insufficient-evidence verdicts labeled as observations — and a repetition
  budget that sizes the next run instead of inviting you to extend this one
- recorded baselines: compare a candidate against a stored run instead of
  paying to re-measure it, with comparability verified from provenance
  before anything runs
- skill and tool invocation measured from preserved trajectories, so a null
  result can be told apart from a treatment that never fired
- benchmark scorecards with outcome, token, cost, duration, and tool-use
  metrics, plus run provenance (harness, model, and tool versions resolved
  from evidence) and honest usage sourcing
- self-contained HTML reports carrying the evidence grade, efficiency, and
  delivery, and a local read-only dashboard (`yacht serve`) that filters and
  groups runs by provenance
- export to the [Every Eval Ever](https://github.com/evaleval/every_eval_ever)
  interchange schema, with Wilson intervals filling the uncertainty the
  ecosystem usually leaves empty

See the [Validating a Tool Claim](docs/tutorials/validating-a-tool-claim.md)
tutorial for the core workflow: turn a tool's claim into a pinned,
preflighted comparison and read the verdict.

## Does Your Skill Actually Work?

Skills are the fastest-growing way to change what a coding agent does —
and the least-measured. YACHT runs the experiment properly: the same
pinned agent on the same tasks, with and without the skill, repeated
until the evidence supports a verdict. In a real run of the bundled
example (10 repetitions, $0.38) the baseline resolved 3 of 10 and the
skill 10 of 10. Seven repetitions were discordant — exactly one side
resolved the task — and all seven favored the skill: a pooled sign test
over those pairs grades the difference `evidence-of-difference` at
p = 0.016. Cost per resolved task: baseline $0.0579, with-skill
$0.0205.

The raw cost delta is honestly refused and flagged as
outcome-confounded (failed runs stop early and spend less); the
efficiency number — ~3x cheaper per resolved task — is the one a
decision needs. Every input is pinned (harness version, task content
digest, skill content), and every attempt leaves re-gradeable
artifacts. See
[Measuring a Skill Claim](docs/tutorials/measuring-a-skill-claim.md)
for the walkthrough, and swap in your own tasks and skill to measure
yours.

## Core Concepts

| Concept | Meaning |
| ------- | ------- |
| Course | A benchmark suite, task set, or evaluation route. |
| Vessel | An agent, model, runtime, or full coding setup being evaluated. |
| Rigging | Tools, prompts, skills, MCP servers, memory systems, and policies added to a vessel. |
| Runtime | The reproducible environment used to run a vessel. |
| Preflight | Machine evidence that a runtime and its rigging are available, configured, and isolated before spending task tokens. |
| Wake | The artifacts left by a run: transcripts, metrics, logs, tool calls, patches, reports. |
| Logbook | The persisted directory containing a run's wake and scorecards. |
| Scorecard | The final comparison view across vessels. |

The nautical vocabulary is part of the project identity, but the artifacts stay
plain JSON so other tools can consume them.

## First Real Run

The quickest way to see YACHT work end to end is the skill A/B: the same
pinned Claude Code on the same task, with and without a skill, graded by
evidence. One repetition costs about $0.04.

Prerequisites:

- Python 3.12 or newer available to `uv`
- `uv`
- Git on `PATH`
- Docker installed, running, and usable by the current user
- network access for the first `uv` dependency sync and the image build
- an Anthropic API key exported as `ANTHROPIC_API_KEY`
- the pinned Harbor launcher image built with the command below

Build the launcher image:

```sh
docker build -t yacht/harbor-launcher:harbor-0.20.0 containers/harbor-launcher
```

Run it:

```sh
LOGBOOK=/private/tmp/yacht-skill-ab-$(date +%Y%m%d-%H%M%S)

uv run yacht doctor examples/custom-eval-skill-ab-smoke.toml

uv run yacht run examples/custom-eval-skill-ab-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY

uv run yacht status --logbook "$LOGBOOK"
uv run yacht report --logbook "$LOGBOOK"
```

Fish shell:

```fish
set -x LOGBOOK /private/tmp/yacht-skill-ab-(date +%Y%m%d-%H%M%S)

uv run yacht doctor examples/custom-eval-skill-ab-smoke.toml

uv run yacht run examples/custom-eval-skill-ab-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY

uv run yacht status --logbook "$LOGBOOK"
uv run yacht report --logbook "$LOGBOOK"
```

One repetition is an observation, not a verdict, and the report says so —
along with the repetition budget that would settle it. Add
`--repetitions 10` (about $0.38) for a graded conclusion; the
[Measuring a Skill Claim](docs/tutorials/measuring-a-skill-claim.md)
walkthrough reads the result line by line.

## A SWE-bench Comparison

The same shape against a public benchmark, using the containerized Pi
runtime. This one needs two more images and SWE-bench metadata on first
run:

- grading runs in the pinned `yacht/swebench-runner` image (`docker build
  -t yacht/swebench-runner:swebench-4.1.0 containers/swebench-runner`),
  which `yacht doctor` verifies is present — there is no manual SWE-bench
  install
- the repo-local Pi runtime image:

```sh
docker build -t yacht/pi-agent-runtime:pi-0.74.0 containers/pi-agent-runtime
```

Run the benchmark smoke:

```sh
LOGBOOK=/private/tmp/yacht-real-benchmark-$(date +%Y%m%d-%H%M%S)

uv run yacht doctor examples/container-pi-fff-real-benchmark-smoke.toml

uv run yacht run examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY

uv run yacht status --logbook "$LOGBOOK"
uv run yacht report --logbook "$LOGBOOK"
uv run yacht report --logbook "$LOGBOOK" --vessel pi-container-fff
```

The default smoke config runs one SWE-bench Lite instance to keep iteration
cheap. For a slightly broader two-instance check, use
`examples/container-pi-fff-real-benchmark-small.toml` with the same commands.

The status report is the first thing to inspect after a run. It shows which
benchmark artifacts exist, what is missing, and the next recommended command.
The benchmark report then summarizes benchmark outcome, agent usage metrics,
notable deltas, per-task outcomes, per-task usage, and the relevant per-vessel
artifact paths. Use `--vessel` and `--task` to narrow the detailed sections
when inspecting a specific run. After a scorecard exists, `yacht status`
recommends a filtered inspection command for the first challenger/task outcome.
For example:

```text
Benchmark scorecard: container-pi-fff-real-benchmark-small / swe-bench-lite
Status: complete
Comparisons: 1 | Vessels: 2 | Measured: 2 | Missing: 0
Usage: Attempts: 4 | Failed: 0 | Tool calls: 15 | Tokens: 63084 | Cost: 0.020688 | Duration: 210.332s
Artifacts: logbook=/private/tmp/yacht-real-benchmark-... | scorecard=/private/tmp/yacht-real-benchmark-.../benchmark-scorecard.json | attempts=/private/tmp/yacht-real-benchmark-.../task-attempt-scorecard.json | launch=/private/tmp/yacht-real-benchmark-.../benchmark-launch-result.json | grading=/private/tmp/yacht-real-benchmark-.../benchmark-grading-collection.json

Notable deltas:
container-pi-vs-pi-fff-benchmark-small: pi-container-fff vs pi-container-baseline | resolved +0 | rate +0.000 | tokens +10988 | cost +0.001650 | duration +7.792s | tool_calls +3

comparison | baseline | challenger | resolved_delta | rate_delta | measured | missing | eligible | preflight
container-pi-vs-pi-fff-benchmark-small | pi-container-baseline | pi-container-fff | +0 | +0.000 | 2/2 | 0 | 2 | preflight-passed:2

Agent usage by task:
comparison | vessel | task | tools | tokens | cost | duration | attempt_artifact
container-pi-vs-pi-fff-benchmark-small | pi-container-fff | django__django-11179 | fffind:1, read:1, bash:1, edit:1 | 25492 | 0.006795 | 75.793s | /private/tmp/yacht-real-benchmark-.../task-attempts/.../django__django-11179.json
```

## Development Smoke

For a no-token local harness check:

```sh
uv run yacht validate examples/local-agent-preflight-smoke.toml
uv run yacht run examples/local-agent-preflight-smoke.toml --logbook logbook
uv run yacht status --logbook logbook
uv run yacht report --logbook logbook
```

This validates the control-plane path without Pi, SWE-bench, Docker grading, or
provider credentials.

## Documentation

- [Project vision](docs/project/vision.md)
- [Roadmap](docs/project/roadmap.md)
- [Audit-backed plan](docs/project/audit-backed-plan.md)
- [Codebase structure](docs/project/codebase-structure.md)
- [Validating a tool claim](docs/tutorials/validating-a-tool-claim.md)
- [Measuring a skill claim](docs/tutorials/measuring-a-skill-claim.md)
- [Command reference](docs/reference/commands.md)
- [Harbor courses: Terminal-Bench and Aider Polyglot](docs/reference/terminal-bench.md)
- [LiveCodeBench course](docs/reference/livecodebench.md)
- [Custom evals](docs/reference/custom-evals.md)
- [Custom harnesses](docs/reference/custom-harnesses.md)
- [Recorded baselines](docs/reference/recorded-baselines.md)
- [Every Eval Ever export](docs/reference/every-eval-ever-export.md)
- [Adding a course](docs/reference/adding-a-course.md)
- [Release checklist](docs/reference/release.md)
- [Schema contract](docs/reference/schemas.md)
- [Architecture decisions](docs/adr/)
- [Changelog](CHANGELOG.md)

## License

YACHT is licensed under the [Apache License 2.0](LICENSE).

## Design Principles

- Prefer reproducible, inspectable evidence over agent attestation.
- Keep runtime provisioning separate from benchmark task grading.
- Make secrets explicit and never copy user-home auth state implicitly.
- Treat benchmarks, smoke tests, and future evaluators as adapters.
- Keep public artifacts language-neutral and stable enough for other tools to
  consume.
- Report success together with cost, tokens, time, tool use, and failure modes.
