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
  --secret anthropic=@env:ANTHROPIC_API_KEY \
  --python-executable "uv run --with swebench python"
uv run yacht benchmark-status --logbook logbook
uv run yacht benchmark-report --logbook logbook
uv run yacht benchmark-report --logbook logbook --format markdown --output logbook/benchmark-report.md
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
uv run yacht benchmark-launcher --logbook logbook --max-workers 1 --python-executable "uv run --with swebench python"
uv run yacht benchmark-launch --logbook logbook
uv run yacht benchmark-collect-grading examples/pi-fff-provisioning.toml --logbook logbook
uv run yacht benchmark-scorecard --logbook logbook
uv run yacht benchmark-status --logbook logbook
uv run yacht benchmark-report --logbook logbook
```

The native benchmark harness owns task containers, test execution, and grading.
YACHT owns the handoff, gates, launch records, normalized grading artifacts, and
scorecards. `benchmark-report` includes comparison outcomes, usage metrics,
per-task outcomes, and per-vessel artifact paths when task attempt data is
available.

## One-Command Workflows

```sh
uv run yacht pi-smoke-eval examples/pi-fff-provisioning.toml --logbook logbook --workspace . --secret anthropic=@env:ANTHROPIC_API_KEY
uv run yacht real-smoke-eval examples/pi-fff-provisioning.toml --logbook logbook --workspace . --secret anthropic=@env:ANTHROPIC_API_KEY
uv run yacht real-smoke-runbook examples/pi-fff-provisioning.toml --logbook logbook --workspace .
uv run yacht real-smoke-runbook examples/pi-fff-provisioning.toml --logbook logbook --workspace . --format markdown
uv run yacht real-benchmark-runbook examples/container-pi-fff-real-benchmark-smoke.toml --logbook logbook --workspace .
uv run yacht real-benchmark-runbook examples/container-pi-fff-real-benchmark-smoke.toml --logbook logbook --workspace . --format markdown
uv run yacht real-benchmark-eval examples/container-pi-fff-real-benchmark-smoke.toml --logbook logbook --workspace . --secret anthropic=@env:ANTHROPIC_API_KEY --python-executable "uv run --with swebench python"
uv run yacht benchmark-status --logbook logbook
```

`real-benchmark-runbook` writes a shareable plan of the exact commands and
expected artifacts before spending benchmark tokens.
`real-benchmark-eval` is the current end-to-end benchmark path: preflight,
task attempts, candidate patch extraction, runtime snapshots, readiness,
native launch, grading collection, scorecard, and top-level summary.
`benchmark-status` is the quick inspection command to run after the workflow; it
prints artifact presence, artifact statuses, and the next recommended command.
