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

## Schema Contract

YACHT keeps its cross-language contract in JSON Schema files under `schemas/`:

- `yacht.regatta.v1.schema.json` for regatta configuration
- `yacht.wake.v1.schema.json` for per-task trace artifacts
- `yacht.scorecard.v1.schema.json` for aggregate results

Generated wake and scorecard JSON documents include a `schema` field such as `yacht.wake.v1` or `yacht.scorecard.v1`. The Python runner validates the current config and generated artifacts, but the persisted contract is intentionally language-neutral so future vessels, runners, and analysis tools do not need to be Python programs.

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
