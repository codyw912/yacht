# Command Reference

This page is a compact map of YACHT's CLI surface. Prefer the README for the
first real benchmark path. The user-facing surface is six commands: `doctor`,
`validate`, `run`, `status`, `report`, and the `internals` group of pipeline
stage commands.

## doctor

```sh
uv run yacht doctor
uv run yacht doctor examples/container-pi-fff-real-benchmark-smoke.toml
uv run yacht doctor --skip-swebench --format json
```

`yacht doctor` checks Python, uv, Git, the Docker CLI and daemon, logbook
writability, and the native SWE-bench harness. Given a config, it also
validates the config and checks its container runtime images and env secrets.
It exits nonzero when a required check fails; unset secrets are warnings
because they can still be injected with `--secret` at eval time.

The SWE-bench harness needs no manual installation: uv resolves it on demand
and caches it. The doctor check performs that resolution, so the one-time
download happens here rather than mid-eval when grading starts.

## validate

```sh
uv run yacht validate examples/local-agent-preflight-smoke.toml
uv run yacht validate examples/container-pi-fff-real-benchmark-smoke.toml --format json
```

Validates a regatta config without running it.

## run

```sh
# Local development smoke (no tokens, no Docker grading)
uv run yacht run examples/local-agent-preflight-smoke.toml --logbook logbook

# Real benchmark smoke
uv run yacht run examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook logbook \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY

# Repeated benchmark runs aggregated under one parent logbook
uv run yacht run examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook logbook \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY \
  --repetitions 3
```

`yacht run` executes the full pipeline and detects the run type from the
config: courses without an adapter run as smoke evals (preflight, task
attempts, smoke readiness), and courses with an adapter run as real benchmarks
(preflight, task attempts, candidate patch extraction, native launch, grading
collection, scorecard). It writes the matching runbook artifact first, prints
progress to stderr, and keeps stdout reserved for the completion summary. Pass
`--format json` for the machine-readable payload. With `--repetitions N`,
benchmark runs execute sequentially into `runs/run-001`, `runs/run-002`, and
so on, then aggregate into `benchmark-aggregate.json` and
`benchmark-report.md`.

Use `examples/container-pi-fff-real-benchmark-small.toml` for a two-instance
SWE-bench Lite smoke instead of the cheaper one-instance default.

Fish shell:

```fish
set -x LOGBOOK /private/tmp/yacht-real-benchmark-(date +%Y%m%d-%H%M%S)

uv run yacht run examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY

uv run yacht status --logbook "$LOGBOOK"
uv run yacht report --logbook "$LOGBOOK"
```

## status

```sh
uv run yacht status
uv run yacht status --logbook logbook
uv run yacht status --logbook logbook --format markdown --output logbook/status.md
```

`yacht status` is the quick inspection command to run after a workflow. It
detects whether the logbook holds a smoke or benchmark run, prints artifact
presence and statuses, and recommends the next command. Without `--logbook`,
it uses `./logbook` if present, then the most recent yacht logbook in the
system temp directory.

## report

```sh
uv run yacht report --logbook logbook
uv run yacht report --logbook logbook --vessel pi-container-fff
uv run yacht report --logbook logbook --vessel pi-container-fff --task django__django-11099
uv run yacht report --logbook logbook --format markdown --output logbook/benchmark-report.md
uv run yacht report --logbook logbook --format html --output logbook/report.html
```

The html format writes a single self-contained file (no scripts, no external
assets) with a verdict banner, per-vessel outcomes and usage, tool-call
evidence showing whether a challenger tool was actually used, and per-task
results. Small samples are labeled so single-run smoke deltas are not
mistaken for statistically meaningful results.

`yacht report` renders the report for a smoke or benchmark logbook. Benchmark
reports start with a decision summary that says whether the challenger
improved, regressed, or tied on resolution, tokens, cost, and duration, then
include comparison outcomes, usage metrics, per-task outcomes, and per-vessel
artifact paths when task attempt data is available. Use `--vessel` and
`--task` to narrow the detailed sections while keeping the full summary for
context. On a repetition parent logbook, the report renders the aggregate.

## serve

```sh
uv run yacht serve --root /private/tmp
uv run yacht serve --root logbooks --port 8080
```

`yacht serve` starts a local, read-only dashboard over a directory of
logbooks (ADR 0010). It scans the root and one level of subdirectories for
logbooks, groups them by regatta and course on the index page, and renders
each run with the same HTML the report command produces. Pages are rendered
from the artifacts on disk at request time — there is no database and no
ingestion step, so the dashboard is always current and deleting a logbook
directory removes it. Logbooks with broken or invalid artifacts appear as
visibly broken entries instead of being skipped. The server binds localhost
by default and is a single-user inspection tool, not a deployment target.

The `/vessels` view lists every vessel run across all logbooks and supports
filtering and grouping by provenance facets through URL query parameters —
`harness`, `harness.version`, `model`, `model.resolved`, `backend`, `image`,
`tool`, and `tool.version` — so "all claude-code runs" and "only
claude-code 2.1.211" are the same page at different depths (for example
`/vessels?harness=claude-code&group=harness.version`). Records whose
provenance collapsed to mixed values group under an explicit unknown bucket
and carry their mixed dimensions in the table, so blended views are always
labeled. Every filter and group state is a bookmarkable URL.

## Internals

`yacht internals <stage>` exposes the pipeline stage commands for debugging
and incremental re-runs. Each stage reads and writes the same logbook
artifacts that `yacht run` produces end to end.

Runtime and preflight:

```sh
uv run yacht internals plan examples/pi-fff-provisioning.toml
uv run yacht internals runtime-instances examples/pi-fff-provisioning.toml --logbook logbook --workspace . --write-logbook
uv run yacht internals preflight examples/pi-fff-provisioning.toml --logbook logbook --secret anthropic=@env:ANTHROPIC_API_KEY
uv run yacht internals preflight-report --logbook logbook
```

- `plan` prints a redacted runtime/preflight plan without launching agents.
- `runtime-instances` prints dry-run host runtime instance resolution.
- `preflight` runs machine preflight checks; add `--agent-preflight <agent>`
  for agent-prompt checks or `--dry-run` for the execution plan.
- `preflight-report` writes the preflight evidence eligibility report.

Task attempts and candidate patches:

```sh
uv run yacht internals task-attempts examples/pi-fff-provisioning.toml --agent pi --logbook logbook --workspace . --secret anthropic=@env:ANTHROPIC_API_KEY
uv run yacht internals task-attempt-scorecard --logbook logbook
uv run yacht internals predictions-from-attempts examples/pi-fff-provisioning.toml --logbook logbook --vessel pi-plus-fff
uv run yacht internals predictions examples/pi-fff-provisioning.toml --input examples/pi-fff-predictions.json --logbook logbook --vessel pi-plus-fff
```

- `task-attempts` runs task attempts and writes per-task agent evidence.
- `task-attempt-scorecard` summarizes task attempt artifacts.
- `predictions-from-attempts` extracts SWE-bench candidate patches from task
  attempt artifacts.
- `predictions` validates and writes externally produced prediction records.

Native benchmark handoff, launch, and grading:

```sh
uv run yacht internals handoff examples/pi-fff-provisioning.toml --logbook logbook
uv run yacht internals benchmark-plan --logbook logbook
uv run yacht internals benchmark-readiness-report --logbook logbook
uv run yacht internals readiness-gate --logbook logbook --output logbook/benchmark-readiness-summary.json
uv run yacht internals benchmark-launcher --logbook logbook --max-workers 1
uv run yacht internals benchmark-launch --logbook logbook
uv run yacht internals benchmark-collect-grading examples/pi-fff-provisioning.toml --logbook logbook
uv run yacht internals grading-report examples/pi-fff-provisioning.toml --from-launcher --vessel pi-plus-fff --logbook logbook
```

- `handoff` writes the planned course adapter handoff artifact.
- `benchmark-plan` writes the dry-run benchmark execution readiness plan.
- `benchmark-readiness-report` renders that plan as a readiness report.
- `readiness-gate` exits nonzero when readiness has blocked vessels.
- `benchmark-launcher` writes native launcher commands without executing them.
- `benchmark-launch` executes the ready native launcher commands.
- `benchmark-collect-grading` collects native reports into validated grading
  artifacts.
- `grading-report` validates and writes a single SWE-bench grading report.

The native benchmark harness owns task containers, test execution, and
grading. YACHT owns the handoff, gates, launch records, normalized grading
artifacts, and scorecards. SWE-bench grading runs in the pinned
`yacht/swebench-runner` container image (build it with
`docker build -t yacht/swebench-runner:swebench-4.1.0 containers/swebench-runner`);
the harness never runs directly on the host.

Scorecards and aggregates:

```sh
uv run yacht internals benchmark-scorecard --logbook logbook
uv run yacht internals benchmark-aggregate --logbook logbook-1 --logbook logbook-2
```

- `benchmark-scorecard` writes the scorecard summary from validated grading
  artifacts.
- `benchmark-aggregate` aggregates completed benchmark scorecards across
  logbooks, including per-run vessel rows with child logbook paths so
  outliers can be inspected.

Smoke readiness:

```sh
uv run yacht internals smoke-readiness-report --logbook logbook
```

- `smoke-readiness-report` checks whether a smoke logbook has usable
  preflight and task evidence.
