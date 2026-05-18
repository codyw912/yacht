# Command Reference

This page is a compact map of YACHT's current CLI surface. Prefer the README
for the first real benchmark path.

## Local Development Smoke

```sh
uv run yacht validate examples/local-agent-preflight-smoke.toml
uv run yacht local-smoke-eval examples/local-agent-preflight-smoke.toml --logbook logbook
uv run yacht smoke-readiness-report --logbook logbook
uv run yacht smoke-report --logbook logbook
uv run yacht smoke-report --logbook logbook --format markdown --output logbook/smoke-report.md
```

## Container Pi Benchmark Smoke

```sh
docker build -t yacht/pi-agent-runtime:pi-0.74.0 containers/pi-agent-runtime

uv run yacht validate examples/container-pi-fff-real-benchmark-smoke.toml
uv run yacht real-benchmark-runbook examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook logbook \
  --workspace .
uv run yacht real-benchmark-eval examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook logbook \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY
uv run yacht real-benchmark-repetitions examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook benchmark-series \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY \
  --repetitions 3
uv run yacht benchmark-status --logbook logbook
uv run yacht benchmark-report --logbook logbook
uv run yacht benchmark-report --logbook logbook --vessel pi-container-fff
uv run yacht benchmark-report --logbook logbook --vessel pi-container-fff --task django__django-11099
uv run yacht benchmark-report --logbook logbook --format markdown --output logbook/benchmark-report.md
```

Use `examples/container-pi-fff-real-benchmark-small.toml` with the same command
sequence when you want a two-instance SWE-bench Lite smoke instead of the
cheaper one-instance default.

Fish shell:

```fish
set -x LOGBOOK /private/tmp/yacht-real-benchmark-(date +%Y%m%d-%H%M%S)

uv run yacht real-benchmark-runbook examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace .

uv run yacht real-benchmark-eval examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY

uv run yacht benchmark-status --logbook "$LOGBOOK"
uv run yacht benchmark-report --logbook "$LOGBOOK"
```

## Runtime and Preflight

```sh
uv run yacht plan examples/pi-fff-provisioning.toml
uv run yacht runtime-instances examples/pi-fff-provisioning.toml --logbook logbook --workspace .
uv run yacht runtime-instances examples/pi-fff-provisioning.toml --logbook logbook --workspace . --write-logbook
uv run yacht preflight examples/pi-fff-provisioning.toml --dry-run --logbook logbook
uv run yacht preflight examples/pi-fff-provisioning.toml --logbook logbook --secret anthropic=@env:ANTHROPIC_API_KEY
uv run yacht preflight examples/pi-fff-provisioning.toml --agent-preflight pi --logbook logbook --secret anthropic=@env:ANTHROPIC_API_KEY
uv run yacht preflight-report --logbook logbook
```

`preflight` proves that the runtime and rigging are available, configured, and
isolated before task tokens are spent. Agent-prompt checks require
`--agent-preflight`.

## Task Attempts and Candidate Patches

```sh
uv run yacht task-attempts examples/pi-fff-provisioning.toml --agent pi --logbook logbook --workspace . --secret anthropic=@env:ANTHROPIC_API_KEY
uv run yacht task-attempt-scorecard --logbook logbook
uv run yacht predictions-from-attempts examples/pi-fff-provisioning.toml --logbook logbook --vessel pi-baseline
uv run yacht predictions-from-attempts examples/pi-fff-provisioning.toml --logbook logbook --vessel pi-plus-fff
```

For SWE-bench courses, task attempts run in checked-out task repositories and
`predictions-from-attempts` extracts unified diff candidate patches.

## Native Benchmark Handoff and Grading

```sh
uv run yacht handoff examples/pi-fff-provisioning.toml --logbook logbook
uv run yacht predictions examples/pi-fff-provisioning.toml --input examples/pi-baseline-predictions.json --logbook logbook --vessel pi-baseline
uv run yacht predictions examples/pi-fff-provisioning.toml --input examples/pi-fff-predictions.json --logbook logbook --vessel pi-plus-fff
uv run yacht runtime-instances examples/pi-fff-provisioning.toml --logbook logbook --workspace . --write-logbook
uv run yacht benchmark-plan --logbook logbook
uv run yacht benchmark-readiness-report --logbook logbook
uv run yacht readiness-gate --logbook logbook --output logbook/benchmark-readiness-summary.json
uv run yacht benchmark-launcher --logbook logbook --max-workers 1
uv run yacht benchmark-launch --logbook logbook
uv run yacht benchmark-collect-grading examples/pi-fff-provisioning.toml --logbook logbook
uv run yacht benchmark-scorecard --logbook logbook
uv run yacht benchmark-status --logbook logbook
uv run yacht benchmark-report --logbook logbook
uv run yacht benchmark-aggregate --logbook logbook-1 --logbook logbook-2
```

The native benchmark harness owns task containers, test execution, and grading.
YACHT owns the handoff, gates, launch records, normalized grading artifacts, and
scorecards. `benchmark-launcher` and `real-benchmark-eval` use
`uv run --with swebench python` by default for SWE-bench launches; pass
`--python-executable` only when using a different managed harness environment.
`benchmark-report` includes comparison outcomes, usage metrics, per-task
outcomes, and per-vessel artifact paths when task attempt data is available.
When per-attempt artifacts are present, it also breaks tokens, cost, duration,
and tool calls down by task. Use `--vessel` and `--task` to narrow the detailed
sections while keeping the full benchmark summary for context. Completed
scorecards and `benchmark-status` include a filtered inspection command for the
first challenger/task outcome.
Use `benchmark-aggregate` with multiple completed benchmark logbooks to inspect
aggregate resolution and usage across repeated runs. Aggregate reports include
per-run vessel rows with child logbook paths so outliers can be inspected.

## One-Command Workflows

```sh
uv run yacht pi-smoke-eval examples/pi-fff-provisioning.toml --logbook logbook --workspace . --secret anthropic=@env:ANTHROPIC_API_KEY
uv run yacht real-smoke-eval examples/pi-fff-provisioning.toml --logbook logbook --workspace . --secret anthropic=@env:ANTHROPIC_API_KEY
uv run yacht real-smoke-runbook examples/pi-fff-provisioning.toml --logbook logbook --workspace .
uv run yacht real-smoke-runbook examples/pi-fff-provisioning.toml --logbook logbook --workspace . --format markdown
uv run yacht real-benchmark-runbook examples/container-pi-fff-real-benchmark-smoke.toml --logbook logbook --workspace .
uv run yacht real-benchmark-runbook examples/container-pi-fff-real-benchmark-smoke.toml --logbook logbook --workspace . --format markdown
uv run yacht real-benchmark-eval examples/container-pi-fff-real-benchmark-smoke.toml --logbook logbook --workspace . --secret anthropic=@env:ANTHROPIC_API_KEY
uv run yacht real-benchmark-repetitions examples/container-pi-fff-real-benchmark-smoke.toml --logbook benchmark-series --workspace . --secret anthropic=@env:ANTHROPIC_API_KEY --repetitions 3
uv run yacht benchmark-status --logbook logbook
uv run yacht benchmark-report --logbook logbook
uv run yacht benchmark-report --logbook logbook --format markdown --output logbook/benchmark-report.md
```

`real-benchmark-runbook` writes a shareable plan of the exact commands and
expected artifacts before spending benchmark tokens.
`real-benchmark-eval` is the current end-to-end benchmark path: preflight,
task attempts, candidate patch extraction, runtime snapshots, readiness,
native launch, grading collection, scorecard, and top-level summary.
Long-running real benchmark commands print progress updates to stderr and keep
stdout reserved for the final JSON artifact.
`real-benchmark-repetitions` runs that same path sequentially into
`runs/run-001`, `runs/run-002`, and so on under a parent logbook, then writes
`real-benchmark-repetitions.json` and `benchmark-aggregate.json` for completed
child runs. When at least one child run completes, it also writes
`benchmark-report.md`. The parent logbook works with `benchmark-status` and
`benchmark-report`; the report renders the aggregate when no single-run
`benchmark-scorecard.json` is present.
`benchmark-status` is the quick inspection command to run after the workflow; it
prints artifact presence, artifact statuses, and the next recommended command.
