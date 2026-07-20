# Terminal-Bench Course

The `terminal-bench` course runs Terminal-Bench 2.0 through its official
harness, Harbor (ADR 0011). Unlike SWE-bench, a Terminal-Bench task is a
containerized environment the agent acts inside, so YACHT delegates both
rollout and verification to Harbor instead of running its own harness
adapter: Harbor builds each task container, installs the pinned agent into
it, runs the agent, runs the task's tests, and records a per-trial result.

## Configuration

```toml
[course.adapter]
kind = "terminal-bench"
dataset = "terminal-bench"   # Harbor registry dataset name
split = "2.0"                # dataset version, pinned
harness = "harbor"

[[course.tasks]]
id = "fix-git"               # Terminal-Bench task name
title = "Recover lost changes and merge them into the master branch"

[runtimes.harbor-claude]
backend = "host-nix"
harness = "claude-code"      # maps to Harbor's installed agent
harness_version = "2.1.215"  # required: the pinned agent version
flake = "path:."
command = ["claude"]
required_secrets = ["anthropic"]
```

- `dataset` and `split` name a pinned dataset version in the Harbor
  registry; there is no floating "latest".
- The vessel's `harness` selects the matching Harbor installed agent
  (`claude-code` and `pi` are supported), and `harness_version` is
  required — job rendering refuses unpinned runtimes.
- The vessel's `model` is passed to Harbor verbatim and uses Harbor's
  provider-prefixed form, e.g. `anthropic/claude-haiku-4-5`.
- Rigging maps onto Harbor's agent configuration: `mcp-server` install
  steps become stdio MCP server entries and rigging env becomes agent
  env. Install methods Harbor cannot express are rejected before launch.
  Note that an MCP server command must be runnable inside the task's own
  container image.
- Provider credentials flow through the environment of the launch
  process (for Anthropic models, export `ANTHROPIC_API_KEY`), consistent
  with Harbor's own convention. YACHT never copies auth state.

## Pipeline shape

Terminal-Bench is a native-rollout course: YACHT skips its own task
attempts and instead writes, per vessel, a task roster and a
`terminal-bench-job.json` describing the agent, pinned version, model,
and rigging surface. The native launcher
(`python -m yacht.courses.terminal_bench.harness`) translates that job
into a Harbor run configuration, invokes a pinned `harbor run`, and
converts Harbor's per-trial `result.json` files into the normalized
grading report the scorecard consumes: a verifier reward of 1 counts as
resolved, a lower reward as unresolved, trial exceptions as errors, and
missing trials as incomplete. Harbor's trial directories — transcripts,
verifier output, rewards — are kept under the vessel's
`harbor-trials/` directory in the logbook for inspection.

After grading, YACHT synthesizes task-attempt artifacts from the trial
results so Terminal-Bench runs carry the same usage and provenance
surface as harness-run attempts: tokens, cost, and duration from
Harbor's recorded totals, the harness version and model resolved from
what Harbor actually installed and ran (ADR 0009 — null when absent,
never guessed), and the trial directory as the transcript path. The
task-attempt scorecard, aggregate reports, and the `yacht serve`
dashboard consume these like any other attempts.

## Example

`examples/terminal-bench-claude-code-versions-smoke.toml` compares two
pinned Claude Code versions on a single task:

```sh
uv run yacht run examples/terminal-bench-claude-code-versions-smoke.toml \
  --logbook /private/tmp/yacht-terminal-bench-smoke \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY
```

Requirements: Docker running, nix, uv, and `ANTHROPIC_API_KEY` exported.
The first run downloads the dataset task and builds its container image.
