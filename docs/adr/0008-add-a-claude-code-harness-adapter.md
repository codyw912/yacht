# ADR 0008: Add a Claude Code Harness Adapter

## Status

Proposed

## Context

Pi is YACHT's only real harness adapter. ADR 0006 and the course/evaluator
split already treat harnesses as registry entries, but a single registered
harness leaves that claim unproven, and it limits who YACHT can serve. The
post-MVP focus is validating claims made by tools, plugins, MCP servers, and
extensions built for coding harnesses, and most of those tools target Claude
Code. Evaluating a Claude Code tool on Pi does not test the claim its author
actually made.

Claude Code supports headless operation: `claude -p <prompt>` runs one
autonomous session, `--output-format stream-json` emits every message,
including tool-use blocks, as JSON lines, and the final result message
carries token usage, total cost, and duration. Authentication accepts an
`ANTHROPIC_API_KEY` environment variable. MCP servers are configured through
JSON config files. All of these fit surfaces YACHT already has: explicit
secret injection, transcript capture, machine evidence parsing, and the
config-file rigging install method from the tool-claim workstream.

Two properties of Claude Code need care. First, autonomous file editing in
headless mode requires bypassing its permission prompts, which is only
acceptable inside an isolated runtime. Second, it releases frequently, so an
unpinned harness would make comparisons unreproducible.

## Decision

We will add a `claude-code` harness adapter alongside Pi.

- **Runtime image.** A repo-local `containers/claude-code-runtime` image
  pins Node and a specific `@anthropic-ai/claude-code` version, tagged with
  that version the way the Pi image is. Host-nix remains a development
  backend; the container is the trusted path.
- **Task attempts.** The adapter launches
  `claude -p <prompt> --output-format stream-json` in the task workspace
  with `--dangerously-skip-permissions`, which is acceptable only because
  the runtime is an isolated container with an isolated home; the adapter
  refuses to run with permission bypass on non-container backends. The
  vessel's model maps to `--model`, and a configurable max-turns cap guards
  cost.
- **Machine evidence.** The stream-json output is captured verbatim as the
  transcript artifact. Tool calls are counted from tool-use messages, and
  tokens, cost, and duration come from the final result message, populating
  the same task-attempt fields Pi populates so scorecards and reports stay
  comparable across harnesses.
- **Preflight.** Machine preflight checks the pinned `claude --version`.
  Agent-prompt preflight uses the existing contract: a headless prompt must
  return JSON with `available` and `configured` true, plus observed tool
  calls when a rigging declares expected tools.
- **Authentication.** `ANTHROPIC_API_KEY` is injected through the existing
  explicit secret machinery. User-home Claude Code auth state is never
  copied, consistent with the project's secrets principle.
- **MCP servers.** The `mcp-server` install method becomes executable for
  this harness by rendering the declared server into Claude Code's MCP
  config inside the trial home, reusing the config-file write machinery and
  its evidence trail. The harness adapter contract gains a hook that turns
  an mcp-server step into harness-specific config-file writes, so other
  harnesses can implement the same method with their own config formats,
  and harnesses without the hook keep blocking the method before tokens are
  spent.

## Consequences

- YACHT can evaluate tool claims on the harness most claim-making tools
  target, and the harness registry claim is proven by a second real
  adapter.
- Comparisons across harnesses (Pi vs Claude Code on the same course)
  become expressible, with the harness recorded per vessel in artifacts.
- The permission-bypass flag concentrates risk in the container boundary;
  the adapter enforces container-only use of the bypass, and isolation
  evidence stays part of preflight.
- A second pinned runtime image joins the release surface and must be
  rebuilt deliberately to pick up new Claude Code versions; `yacht doctor`
  checks its presence per config.
- Claude Code's stream-json format is an external contract; a format change
  breaks evidence parsing, so the adapter validates the result message and
  fails attempts loudly rather than recording partial usage silently.
- Rigging recipes that only declare `config-file` and `mcp-server` installs
  become portable across harnesses; `agent-extension` steps remain
  harness-specific by design.
