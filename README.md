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

YACHT now has a real end-to-end benchmark smoke path:

- containerized Pi baseline vs containerized Pi+fff
- explicit secret injection
- runtime and rigging preflight
- SWE-bench Lite task context loading
- per-task repository checkout at the benchmark base commit
- agent task attempts and transcripts
- candidate patch extraction
- native SWE-bench Docker grading
- benchmark scorecards with outcome, token, cost, and tool-use metrics

The first verified real benchmark smoke used `django__django-11099`; both
baseline and fff vessels resolved the task. That is a foundation, not a final
tool. The next phase is making this easier for humans to run, inspect, and
extend.

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

## First Real Benchmark

Prerequisites:

- `uv`
- Docker
- the repo-local Pi runtime image
- an Anthropic API key exported as `ANTHROPIC_API_KEY`

Build the Pi runtime image:

```sh
docker build -t yacht/pi-agent-runtime:pi-0.74.0 containers/pi-agent-runtime
```

Run the benchmark smoke:

```sh
LOGBOOK=/private/tmp/yacht-real-benchmark-$(date +%Y%m%d-%H%M%S)

uv run yacht real-benchmark-runbook examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace .

uv run yacht real-benchmark-eval examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY \
  --python-executable "uv run --with swebench python"

uv run yacht benchmark-status --logbook "$LOGBOOK"
uv run yacht benchmark-report --logbook "$LOGBOOK"
uv run yacht benchmark-report --logbook "$LOGBOOK" --vessel pi-container-fff
```

Fish shell:

```fish
set -x LOGBOOK /private/tmp/yacht-real-benchmark-(date +%Y%m%d-%H%M%S)

uv run yacht real-benchmark-runbook examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace .

uv run yacht real-benchmark-eval examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY \
  --python-executable "uv run --with swebench python"

uv run yacht benchmark-status --logbook "$LOGBOOK"
uv run yacht benchmark-report --logbook "$LOGBOOK"
```

The status report is the first thing to inspect after a run. It shows which
benchmark artifacts exist, what is missing, and the next recommended command.
The benchmark report then summarizes benchmark outcome, agent usage metrics,
per-task outcomes, and the relevant per-vessel artifact paths.
Use `--vessel` and `--task` to narrow the detailed sections when inspecting a
specific run.
For example:

```text
Benchmark scorecard: container-pi-fff-real-benchmark-smoke / swe-bench-lite
Status: complete
Comparisons: 1 | Vessels: 2 | Measured: 2 | Missing: 0
Usage: Attempts: 2 | Failed: 0 | Tool calls: 7 | Tokens: 15643 | Cost: 0.010336 | Duration: 0.000s
Artifacts: logbook=/private/tmp/yacht-real-benchmark-... | scorecard=/private/tmp/yacht-real-benchmark-.../benchmark-scorecard.json | attempts=/private/tmp/yacht-real-benchmark-.../task-attempt-scorecard.json | launch=/private/tmp/yacht-real-benchmark-.../benchmark-launch-result.json | grading=/private/tmp/yacht-real-benchmark-.../benchmark-grading-collection.json

comparison | baseline | challenger | resolved_delta | rate_delta | measured | missing | eligible | preflight
container-pi-vs-pi-fff-benchmark-smoke | pi-container-baseline | pi-container-fff | +0 | +0.000 | 2/2 | 0 | 2 | preflight-passed:2
```

## Development Smoke

For a no-token local harness check:

```sh
uv run yacht validate examples/local-agent-preflight-smoke.toml
uv run yacht local-smoke-eval examples/local-agent-preflight-smoke.toml --logbook logbook
uv run yacht smoke-readiness-report --logbook logbook
uv run yacht smoke-report --logbook logbook
```

This validates the control-plane path without Pi, SWE-bench, Docker grading, or
provider credentials.

## Documentation

- [Project vision](docs/project/vision.md)
- [Roadmap](docs/project/roadmap.md)
- [Command reference](docs/reference/commands.md)
- [Schema contract](docs/reference/schemas.md)
- [Architecture decisions](docs/adr/)

## Design Principles

- Prefer reproducible, inspectable evidence over agent attestation.
- Keep runtime provisioning separate from benchmark task grading.
- Make secrets explicit and never copy user-home auth state implicitly.
- Treat benchmarks, smoke tests, and future evaluators as adapters.
- Keep public artifacts language-neutral and stable enough for other tools to
  consume.
- Report success together with cost, tokens, time, tool use, and failure modes.
