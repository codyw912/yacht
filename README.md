# YACHT

Yet Another Coding Harness Testbed.

YACHT is a modular, configurable platform for evaluating agentic coding setups under controlled, reproducible conditions. It exists to test whether claimed improvements in coding agents actually hold up: higher benchmark scores, lower token usage, faster completion times, better reliability, stronger tool use, or fewer failed runs.

The premise is simple: run the same benchmark course across different vessels, compare the wake, and publish the scorecard.

## Why YACHT Exists

Agentic coding stacks are changing quickly. New tools, skills, prompts, memory systems, MCP servers, harness policies, and model configurations often claim to improve performance, but those claims are hard to compare without repeatable experiments.

YACHT provides a shared structure for those comparisons:

- Define a benchmark **course** once.
- Run it across multiple **vessels**.
- Configure each vessel with different **rigging**.
- Execute controlled **sea trials** or full **regattas**.
- Capture traces and telemetry in the **wake**.
- Persist reports in the **logbook**.
- Present final comparisons in a **scorecard**.

The tone is intentionally cheeky, because yes, this is yet another eval harness. The goal is still serious: make claims about agent-tool improvements testable, reproducible, and easy to inspect.

## Core Concepts

| Concept | Meaning |
| ------- | ------- |
| Course | A benchmark suite, task set, or evaluation route that vessels run through. |
| Vessel | An agent, harness, model, or full coding setup being evaluated. |
| Rigging | Tools, skills, prompts, policies, memory systems, MCP servers, and other enhancements attached to a vessel. |
| Sea trial | An individual experiment run. |
| Regatta | A full comparison across multiple vessels and/or rigging variants. |
| Wake | Execution traces, telemetry, logs, artifacts, and other evidence left by a run. |
| Logbook | Persisted reports and historical run records. |
| Scorecard | Final results view comparing outcomes across vessels. |

## First Executable Slice

YACHT currently includes a minimal CLI that can run a deterministic mock regatta from a TOML config. This is not a real agent backend yet; it is the harness skeleton for loading a course, comparing vessels, writing wake artifacts, and producing a scorecard.

Run the sample regatta:

```sh
uv run yacht validate examples/memory-smoke-test.toml
uv run yacht validate examples/memory-smoke-test.toml --format json
uv run yacht run examples/memory-smoke-test.toml --logbook logbook
```

The command writes:

- `logbook/wake/*.json` for per-vessel, per-task trace evidence
- `logbook/scorecard.json` for the aggregate comparison

The bundled sample compares a baseline mock vessel against the same mock vessel with `memory` rigging. The deterministic mock runner models that rigging as lower token usage with slightly longer runtime, giving the scorecard something concrete to compare before real agent integrations exist.

For preflight development, `examples/local-agent-preflight-smoke.toml` provides
a tiny baseline-vs-rigged fixture that can exercise the full preflight path with
the built-in `local-smoke` agent preflight adapter:

```sh
uv run yacht preflight examples/local-agent-preflight-smoke.toml --agent-preflight local-smoke --logbook logbook
uv run yacht local-smoke-eval examples/local-agent-preflight-smoke.toml --logbook logbook
uv run yacht task-attempts examples/local-agent-preflight-smoke.toml --agent local-smoke --logbook logbook
uv run yacht task-attempt-scorecard --logbook logbook
```

It avoids command checks, Docker, SWE-bench, Pi, and Nix execution while still
validating isolated runtime state plus an `agent-prompt` check. The
`local-smoke-eval` command prepares the configured runtimes, executes the local
smoke task once per comparison vessel, writes transcripts, emits
`yacht.task-attempt.v1` artifacts under `logbook/task-attempts/`, and summarizes
them into `logbook/task-attempt-scorecard.json`. The lower-level
`task-attempts` and `task-attempt-scorecard` commands are available when those
steps need to be run separately.

YACHT also accepts a config-only provisioning scaffold for future real agent
runs. `examples/pi-fff-provisioning.toml` describes a baseline Pi vessel and a
Pi+fff vessel using an explicit `host-nix` runtime recipe, a named fff rigging
recipe, preflight smoke checks, a SWE-bench Lite course adapter, a comparison
group, and explicit secret references. Validation checks the model without
running Pi, installing fff, or executing SWE-bench:

```sh
uv run yacht validate examples/pi-fff-provisioning.toml
uv run yacht plan examples/pi-fff-provisioning.toml
uv run yacht runtime-instances examples/pi-fff-provisioning.toml --logbook logbook --workspace .
uv run yacht runtime-instances examples/pi-fff-provisioning.toml --logbook logbook --workspace . --write-logbook
uv run yacht handoff examples/pi-fff-provisioning.toml --logbook logbook
uv run yacht predictions examples/pi-fff-provisioning.toml --input examples/pi-fff-predictions.json --logbook logbook
uv run yacht grading-report examples/pi-fff-provisioning.toml --input examples/pi-fff-native-report.json --logbook logbook
uv run yacht predictions examples/pi-fff-provisioning.toml --input examples/pi-baseline-predictions.json --logbook logbook --vessel pi-baseline
uv run yacht grading-report examples/pi-fff-provisioning.toml --input examples/pi-baseline-native-report.json --logbook logbook --vessel pi-baseline
uv run yacht predictions examples/pi-fff-provisioning.toml --input examples/pi-fff-predictions.json --logbook logbook --vessel pi-plus-fff
uv run yacht grading-report examples/pi-fff-provisioning.toml --input examples/pi-fff-native-report.json --logbook logbook --vessel pi-plus-fff
uv run yacht benchmark-plan --logbook logbook
uv run yacht benchmark-launcher --logbook logbook --max-workers 1
uv run yacht preflight-report --logbook logbook
uv run yacht grading-report examples/pi-fff-provisioning.toml --from-launcher --logbook logbook --vessel pi-plus-fff
uv run yacht benchmark-scorecard --logbook logbook
uv run yacht benchmark-readiness-report --logbook logbook
uv run yacht benchmark-readiness-report --logbook logbook --format json
uv run yacht benchmark-readiness-report --logbook logbook --format summary-json
uv run yacht readiness-gate --logbook logbook --output logbook/benchmark-readiness-summary.json
uv run yacht benchmark-report --logbook logbook
uv run yacht benchmark-report --logbook logbook --format markdown
uv run yacht benchmark-report --logbook logbook --format markdown --output logbook/benchmark-report.md
uv run yacht preflight examples/pi-fff-provisioning.toml --dry-run --logbook logbook
uv run yacht preflight examples/pi-fff-provisioning.toml --logbook logbook --secret anthropic="$ANTHROPIC_API_KEY"
uv run yacht preflight examples/pi-fff-provisioning.toml --agent-preflight pi --logbook logbook --secret anthropic="$ANTHROPIC_API_KEY"
uv run yacht task-attempts examples/pi-fff-provisioning.toml --agent pi --logbook logbook --workspace . --secret anthropic="$ANTHROPIC_API_KEY"
uv run yacht pi-smoke-eval examples/pi-fff-provisioning.toml --logbook logbook --workspace . --secret anthropic="$ANTHROPIC_API_KEY"
```

`yacht plan` is a dry run. It prints the resolved runtime and preflight plan
with isolated runtime placeholders, redacted secret references, and any
benchmark handoff metadata, but does not launch agents, install rigging, execute
preflight checks, invoke Docker, or write a logbook.
`yacht runtime-instances` is also a dry run. It resolves each comparison
vessel's concrete host runtime paths, Nix command prefix, runtime command,
isolated environment, cleanup paths, and redacted secret placeholders without
creating runtime directories or launching an agent. Pass `--write-logbook` to
persist that redacted snapshot at `logbook/runtime-instances.json`; this creates
only the artifact path, not the resolved per-trial runtime directories.
`yacht handoff` writes `logbook/course-handoff.json`, a versioned planned
contract for the native benchmark harness handoff. It records adapter inputs,
tasks, comparison vessels, expected future output paths, and delegated grading
metadata without invoking Docker or SWE-bench.
`yacht predictions` validates explicit SWE-bench prediction records against the
course handoff task ids, writes the native candidate patch JSONL file at
`logbook/course-handoff/swe-bench/candidate-patches.jsonl`, and still does not
invoke Docker or grade tasks. Input records must include `instance_id`,
`model_name_or_path`, and `model_patch`. Pass `--vessel <name>` to write
per-vessel predictions under
`logbook/course-handoff/swe-bench/vessels/<name>/candidate-patches.jsonl`;
in that mode `model_name_or_path` must match the vessel name.
`yacht grading-report` validates a native SWE-bench report JSON against the
course handoff and candidate patch ids, then writes the normalized report to
`logbook/course-handoff/swe-bench/grading-report.json`. This is still a contract
check only; YACHT does not run the native harness in this slice. Pass
`--vessel <name>` to validate against that vessel's candidate patch file and
write `logbook/course-handoff/swe-bench/vessels/<name>/grading-report.json`.
After a native launcher handoff has been written and the SWE-bench command has
produced its report, pass `--from-launcher --vessel <name>` instead of `--input`
to read the expected report path from `logbook/benchmark-launcher-handoff.json`.
`yacht benchmark-plan` reads the handoff and per-vessel benchmark artifact paths,
then writes `logbook/benchmark-execution-plan.json`, a dry-run readiness report
showing which vessels are missing candidate patches, ready for native grading, or
already graded. A vessel with candidate patches is not ready until its
comparison-scoped preflight evidence artifact exists, validates, matches the
vessel, has `status: passed`, and the logbook contains a matching
`runtime-instances.json` snapshot. It does not invoke agents, Docker, or the
native benchmark harness.
`yacht benchmark-readiness-report` reads `logbook/benchmark-execution-plan.json`
and prints a compact per-vessel table for the spend gates: candidate patch,
runtime snapshot, preflight evidence, and grading status. It supports text,
Markdown, full JSON, and `summary-json` output, plus `--output` for durable
notes. Use `--format json` when automation needs the full validated
`yacht.benchmark-execution-plan.v1` document. Use `--format summary-json` when
automation only needs launch/no-launch counts and the blocked vessel artifact
paths from the `yacht.benchmark-readiness-summary.v1` contract.

For automation, write the readiness gate artifacts in order:

```sh
uv run yacht runtime-instances examples/pi-fff-provisioning.toml --logbook logbook --workspace . --write-logbook
uv run yacht benchmark-plan --logbook logbook
uv run yacht readiness-gate --logbook logbook --output logbook/benchmark-readiness-summary.json
```

The final file is the compact launch gate: if `blocked_vessel_count` is greater
than zero, inspect `blocked_vessels[*].artifact_paths` before spending benchmark
tokens or emitting native launcher commands. `yacht readiness-gate` writes the
same summary JSON and exits nonzero when any vessel is blocked. Its exit codes
are intentionally CI-friendly: `0` means no vessels are blocked, and `1` means
the gate is blocked or the readiness input artifact is missing or invalid. When
`--output` is provided and the input is valid, the summary JSON file is written
on both passing and blocked gates; blocked gates still return exit `1` after
writing the artifact.

In shell or CI, fail early when the gate is blocked:

```sh
jq -e '.blocked_vessel_count == 0' logbook/benchmark-readiness-summary.json
```

Example `summary-json` output:

```json
{
  "schema": "yacht.benchmark-readiness-summary.v1",
  "regatta": "pi-fff-comparison",
  "course": "swe-bench-lite",
  "status": "mixed",
  "total_vessels": 2,
  "launchable_vessels": 0,
  "graded_vessels": 1,
  "blocked_vessel_count": 1,
  "blocked_vessels": [
    {
      "comparison": "pi-vs-pi-fff",
      "vessel": "pi-baseline",
      "status": "missing-runtime-snapshot",
      "details": "runtime instances: logbook/runtime-instances.json; grading report: logbook/course-handoff/swe-bench/vessels/pi-baseline/grading-report.json",
      "artifact_paths": {
        "candidate_patches": "logbook/course-handoff/swe-bench/vessels/pi-baseline/candidate-patches.jsonl",
        "preflight": "logbook/preflight/pi-vs-pi-fff/pi-baseline.json",
        "runtime_instances": "logbook/runtime-instances.json",
        "grading_report": "logbook/course-handoff/swe-bench/vessels/pi-baseline/grading-report.json"
      }
    }
  ]
}
```

`yacht benchmark-launcher` writes `logbook/benchmark-launcher-handoff.json`, an
artifact-only native harness handoff containing the exact
`python -m swebench.harness.run_evaluation` command YACHT expects for every
ready vessel. It applies the same preflight evidence and runtime snapshot gates
before emitting native commands. It includes dataset, split, predictions path,
max workers, run id, report directory, and instance ids, but does not run Docker
or SWE-bench.
`yacht preflight-report` writes `logbook/preflight-evidence-report.json`, a
human-auditable eligibility report for each comparison vessel. It explains
whether the preflight artifact is missing, failed, invalid, or passed without
running checks or benchmark tasks.
`yacht benchmark-scorecard` reads the handoff and validated grading artifacts
and writes `logbook/benchmark-scorecard.json`, a benchmark-result summary shaped
for comparisons. It combines all per-vessel grading artifacts it finds and keeps
missing comparison vessels explicit until each vessel has its own validated
grading artifact. Each vessel row also carries compact preflight eligibility
context from the evidence report, including whether it was eligible to spend
benchmark tokens and the preflight reason. Each comparison includes aggregate
counts for total, eligible, blocked, measured, and missing-result vessels. The
comparison also includes a baseline-to-challenger delta for resolved instances
and resolution rate. The scorecard also includes top-level aggregate counts
across all comparisons. `yacht benchmark-report` reads that scorecard and prints
a compact human-readable comparison table, including preflight reason counts for
each comparison. It supports optional Markdown output for publishing or PR
notes. Pass `--output` to write the rendered report as a durable artifact.
`yacht preflight --dry-run` prints the resolved preflight execution plan for the
selected preflight mode, including which checks would be included or omitted and
where artifacts/transcripts would be written.
The initial `HostNixRuntimeBackend` can prepare those isolated runtime
directories and explicit env-secret injections for a trial. Local smoke task
execution can now launch against that prepared runtime, and the Pi adapter has
an injected task-launcher boundary for tests and future real subprocess runs.
Machine-only preflight execution can now validate `command`, `env`, and
`path-isolation` checks against a prepared runtime and write
`yacht.preflight.v1` evidence artifacts. This still does not run benchmark
tasks; it only proves the configured runtime and machine-checkable rigging are
ready enough to spend task-run tokens. Preflight summaries include every
configured check and mark agent-prompt checks as omitted when agent preflight is
not enabled. Each summary vessel points to its `yacht.preflight.v1` evidence
artifact, and that artifact records the runtime context plus each check's
runtime or rigging origin.
Agent-surface `agent-prompt` checks can also be executed through an injected
runner that returns response, transcript, and tool-call evidence. The Pi adapter
exposes that runner boundary through an injected headless prompt launcher and a
subprocess launcher that writes transcript evidence. CLI preflight remains
machine-only by default; pass `--agent-preflight pi` to opt into `agent-prompt`
checks through the Pi subprocess launcher, or `--agent-preflight local-smoke`
for the built-in local development fixture. Agent-prompt responses must be JSON
objects with `available: true` and `configured: true`; YACHT records the parsed
response and fails the preflight if that contract is not met.
Task execution will write one validated `yacht.task-attempt.v1` artifact per
vessel/task attempt. The artifact records the comparison, task, runtime context,
agent exit code, response, tool calls, transcript path, metrics, and redacted
secret references. Pass `--agent pi` to launch those attempts through the Pi
subprocess adapter; this requires explicit `--secret` values for configured
secret references and still does not run SWE-bench Docker grading.
`yacht pi-smoke-eval` is the Pi convenience wrapper for the same path: it runs
Pi task attempts and immediately writes `task-attempt-scorecard.json`. This is
the durable bridge between a prepared runtime and later benchmark-specific
candidate outputs.

## Schema Contract

YACHT keeps its cross-language contract in JSON Schema files under `schemas/`:

- `yacht.regatta.v1.schema.json` for regatta configuration
- `yacht.wake.v1.schema.json` for per-task trace artifacts
- `yacht.scorecard.v1.schema.json` for aggregate results
- `yacht.preflight.v1.schema.json` for runtime and rigging trust evidence
- `yacht.preflight-summary.v1.schema.json` for preflight CLI summary output
- `yacht.preflight-evidence-report.v1.schema.json` for benchmark eligibility audits
- `yacht.course-handoff.v1.schema.json` for native benchmark handoff artifacts
- `yacht.swe-bench-grading.v1.schema.json` for validated SWE-bench grading reports
- `yacht.benchmark-execution-plan.v1.schema.json` for benchmark readiness plans
- `yacht.benchmark-readiness-summary.v1.schema.json` for compact readiness automation
  summaries
- `yacht.benchmark-launcher-handoff.v1.schema.json` for native launcher handoffs
- `yacht.benchmark-scorecard.v1.schema.json` for benchmark scorecard summaries
- `yacht.runtime-instances.v1.schema.json` for redacted runtime instance dry-run snapshots
- `yacht.task-attempt.v1.schema.json` for per-agent task attempt evidence
- `yacht.task-attempt-scorecard.v1.schema.json` for task attempt summaries

Generated wake, scorecard, preflight evidence, preflight summary, preflight
evidence report, course handoff, task attempt, and task attempt scorecard JSON
documents include a `schema` field such as `yacht.wake.v1`,
`yacht.scorecard.v1`, `yacht.preflight-summary.v1`,
`yacht.preflight-evidence-report.v1`, `yacht.course-handoff.v1`,
`yacht.task-attempt.v1`, or `yacht.task-attempt-scorecard.v1`. Validated
SWE-bench grading reports, benchmark readiness plans, readiness summaries,
native launcher handoffs, and benchmark scorecard summaries include
`yacht.swe-bench-grading.v1`, `yacht.benchmark-execution-plan.v1`,
`yacht.benchmark-readiness-summary.v1`, `yacht.benchmark-launcher-handoff.v1`,
and `yacht.benchmark-scorecard.v1`. Runtime instance dry-run snapshots include
`yacht.runtime-instances.v1`. The Python runner validates the current config
and generated artifacts, but the persisted contract is intentionally
language-neutral so future vessels, runners, and analysis tools do not need to
be Python programs.

Regatta configs may optionally include provisioning sections:

- `secrets` names explicit env/file secret references without storing values.
- `runtimes` defines agent runtime recipes such as `host-nix` plus a flake and command.
- `riggings` defines named setup and environment changes that vessels can reference.
- `course.adapter` optionally records a native benchmark harness such as SWE-bench.
- `preflight` defines the regatta-level failure policy for required checks.
- `comparisons` defines which vessels must be interpreted together.

The default preflight failure policy is `abort-group`: if any required preflight
check fails for a vessel in a comparison, YACHT should skip task execution for
that comparison group rather than spend tokens on an invalid paired result.

## Evaluation Goals

YACHT should make it straightforward to compare setups on:

- Task success and benchmark score
- Token usage
- Completion time
- Reliability across repeated runs
- Failure modes and recoverability
- Tool, skill, prompt, and memory impact
- Cost where provider pricing is available

## Design Direction

YACHT should favor reproducibility over spectacle:

- Configurations should be explicit and versionable.
- Runs should emit inspectable artifacts.
- Results should distinguish raw measurements from derived conclusions.
- Benchmarks should be reusable across many vessels.
- Comparison reports should make it clear what changed between variants.

The nautical vocabulary is part of the product identity, but it should clarify the domain rather than obscure it. When in doubt, use the cheeky term in user-facing concepts and keep precise technical names in code and schemas.
