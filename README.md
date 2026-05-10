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
```

It avoids command checks, Docker, SWE-bench, Pi, and Nix execution while still
validating isolated runtime state plus an `agent-prompt` check.

YACHT also accepts a config-only provisioning scaffold for future real agent
runs. `examples/pi-fff-provisioning.toml` describes a baseline Pi vessel and a
Pi+fff vessel using an explicit `host-nix` runtime recipe, a named fff rigging
recipe, preflight smoke checks, a SWE-bench Lite course adapter, a comparison
group, and explicit secret references. Validation checks the model without
running Pi, installing fff, or executing SWE-bench:

```sh
uv run yacht validate examples/pi-fff-provisioning.toml
uv run yacht plan examples/pi-fff-provisioning.toml
uv run yacht handoff examples/pi-fff-provisioning.toml --logbook logbook
uv run yacht preflight examples/pi-fff-provisioning.toml --dry-run --logbook logbook
uv run yacht preflight examples/pi-fff-provisioning.toml --logbook logbook --secret anthropic="$ANTHROPIC_API_KEY"
uv run yacht preflight examples/pi-fff-provisioning.toml --agent-preflight pi --logbook logbook --secret anthropic="$ANTHROPIC_API_KEY"
```

`yacht plan` is a dry run. It prints the resolved runtime and preflight plan
with isolated runtime placeholders, redacted secret references, and any
benchmark handoff metadata, but does not launch agents, install rigging, execute
preflight checks, invoke Docker, or write a logbook.
`yacht handoff` writes `logbook/course-handoff.json`, a versioned planned
contract for the native benchmark harness handoff. It records adapter inputs,
tasks, comparison vessels, expected future output paths, and delegated grading
metadata without invoking Docker or SWE-bench.
`yacht preflight --dry-run` prints the resolved preflight execution plan for the
selected preflight mode, including which checks would be included or omitted and
where artifacts/transcripts would be written.
The initial `HostNixRuntimeBackend` can prepare those isolated runtime
directories and explicit env-secret injections for a trial; launching the agent
inside that prepared runtime is a later slice.
Machine-only preflight execution can now validate `command`, `env`, and
`path-isolation` checks against a prepared runtime and write
`yacht.preflight.v1` evidence artifacts. This still does not run benchmark
tasks; it only proves the configured runtime and machine-checkable rigging are
ready enough to spend task-run tokens. Preflight summaries include every
configured check and mark agent-prompt checks as omitted when agent preflight is
not enabled.
Agent-surface `agent-prompt` checks can also be executed through an injected
runner that returns response, transcript, and tool-call evidence. The Pi adapter
exposes that runner boundary through an injected headless prompt launcher and a
subprocess launcher that writes transcript evidence. CLI preflight remains
machine-only by default; pass `--agent-preflight pi` to opt into `agent-prompt`
checks through the Pi subprocess launcher, or `--agent-preflight local-smoke`
for the built-in local development fixture. Agent-prompt responses must be JSON
objects with `available: true` and `configured: true`; YACHT records the parsed
response and fails the preflight if that contract is not met.

## Schema Contract

YACHT keeps its cross-language contract in JSON Schema files under `schemas/`:

- `yacht.regatta.v1.schema.json` for regatta configuration
- `yacht.wake.v1.schema.json` for per-task trace artifacts
- `yacht.scorecard.v1.schema.json` for aggregate results
- `yacht.preflight.v1.schema.json` for runtime and rigging trust evidence
- `yacht.preflight-summary.v1.schema.json` for preflight CLI summary output
- `yacht.course-handoff.v1.schema.json` for native benchmark handoff artifacts

Generated wake, scorecard, preflight evidence, preflight summary, and course
handoff JSON documents include a `schema` field such as `yacht.wake.v1`,
`yacht.scorecard.v1`, `yacht.preflight-summary.v1`, or
`yacht.course-handoff.v1`. The Python runner validates the current config and
generated artifacts, but the persisted contract is intentionally
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
