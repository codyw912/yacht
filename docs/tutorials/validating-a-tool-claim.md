# Validating a Tool Claim

A tool ships with a claim: "our MCP server makes coding agents faster and
more accurate." This tutorial turns that claim into a measured comparison —
the same harness, the same model, the same tasks, with and without the tool —
and produces machine evidence you can read in one HTML page.

The walkthrough uses the
[Claude Code MCP example](../../examples/container-claude-code-mcp-real-task-smoke.toml)
with a placeholder tool (`@ff-labs/mcp-fff`, which does not exist on npm). To
validate a real tool, substitute its package and server command in the
rigging section — nothing else changes.

## What you need

- Docker, with the pinned Claude Code runtime image built:

  ```sh
  docker build -t yacht/claude-code-runtime:claude-2.1.211 containers/claude-code-runtime
  ```

- An `ANTHROPIC_API_KEY` in your environment. It is injected through YACHT's
  explicit secret machinery; your user-level Claude Code login and state are
  never copied into the trial.

## The comparison in one file

A regatta config declares everything the comparison needs. The example pits
two vessels against each other on the same course:

```toml
[[vessels]]
name = "claude-code-container-baseline"
model = "claude-haiku-4-5"
runtime = "claude-code-container"

[[vessels]]
name = "claude-code-container-fff-mcp"
model = "claude-haiku-4-5"
runtime = "claude-code-container"
rigging = ["fff-mcp"]
```

The only difference between the vessels is the rigging — the tool under
test. Everything that could otherwise vary is pinned:

- **The harness version** is pinned by the runtime image tag
  (`yacht/claude-code-runtime:claude-2.1.211`). Rebuilding the image is a
  deliberate act, so two runs weeks apart still measure the same Claude Code.
- **The tool version** is pinned by the package install step:

  ```toml
  [[riggings.fff-mcp.install]]
  method = "package"
  target = "npm:@ff-labs/mcp-fff@0.3.0"

  [[riggings.fff-mcp.install]]
  method = "mcp-server"
  target = "fff"
  command = ["mcp-fff", "--stdio"]
  ```

  The pinned package installs once at setup time, into npm state that lives
  inside the trial's isolated home. The `mcp-server` step then references
  the installed binary, so the server starts offline. Avoid `npx -y <pkg>`
  as an MCP command: it fetches a floating version from npm at session
  start, which reintroduces both network access and version drift into the
  measured run.

The `mcp-server` step is rendered by the harness adapter into Claude Code's
configuration inside the trial home (`.claude.json`, user scope), never into
the task workspace — so benchmark diffs stay clean. Both the package install
and each declared server are recorded in the task attempt's
`runtime_context.setup_results`, so every artifact states exactly which tool
version the vessel was carrying.

## Preflight: prove the tool is live before spending tokens

A comparison where the tool silently failed to load measures nothing. The
rigging declares checks that must pass before any task attempt runs:

```toml
[riggings.fff-mcp.preflight]
required = true
checks = [
  { name = "fff-mcp-connected", kind = "command", command = ["claude", "mcp", "list"] },
  { name = "fff-mcp-headless-smoke", kind = "agent-prompt", prompt = "preflights/claude-code-fff-mcp.md", expect_tool_calls = ["mcp__fff__fffind"] },
]
```

The command check verifies Claude Code discovers the server and can connect
to it. The agent-prompt check goes further: a headless session must actually
call the tool (MCP tools surface as `mcp__<server>__<tool>`) and report
itself available and configured. If either fails, the run aborts before
tokens are spent, and the failure evidence lands in the logbook.

## Run it

```sh
uv run yacht doctor examples/container-claude-code-mcp-real-task-smoke.toml
uv run yacht run examples/container-claude-code-mcp-real-task-smoke.toml \
  --secret anthropic=@env:ANTHROPIC_API_KEY \
  --repetitions 3
```

`doctor` confirms the runtime image and secrets are in place. `run` executes
preflight, then every task for both vessels, once per repetition.
Repetitions matter: a single run of a nondeterministic system is an
anecdote, and the report will say so.

## Read the verdict

```sh
uv run yacht report --format html --output report.html
```

The report opens with a verdict banner — improved, regressed, or tied — and
qualifies it honestly: the statistical evidence grade (evidence of
difference, not distinguishable, or insufficient evidence with the
discordant count that would settle it), and a small-sample badge when the
task count is low. Below that, the tool-call evidence table shows whether
the rigged vessel actually used the tool during tasks, alongside tokens,
cost, and duration per vessel — all parsed from the harness's own machine
output, not from the model's self-report.

For an MCP rigging the delivery unit is the server (ADR 0022): the
`mcp-server` install step's target contributes a namespace expectation
automatically, any `mcp__<server>__` call in the preserved trajectory
counts the server as delivered, and the report lists which of its tools
were actually observed — no per-tool declaration to write or keep
current. pi has no native MCP support, so carrying a server there
needs a declared provider — the `pi-mcp-adapter` rigging in
`examples/custom-eval-pi-mcp-ab-smoke.toml` (ADR 0024).

A claim validated here means: on this course, with this harness and model at
these pinned versions, the tool changed the outcome by this much, and the
tool was demonstrably live while it happened. That sentence — with every
version in it — is what the artifacts record.
