# ADR 0022: Measure MCP Server Delivery by Tool Namespace

## Status

Accepted

## Context

ADR 0019 made treatment delivery measurable for skills and extensions
and deliberately left MCP servers out of that slice. They are the
remaining gap, and an awkward one: MCP servers are among the most
common things a team rigs onto an agent, and "we added the server and
things got better" is exactly the claim yacht exists to check.

The two existing derivations do not transfer. A skill has one
invocation marker read from the SKILL.md it installs. An extension
declares its `expected_tool_calls` up front. An MCP server has neither:
it exposes a set of tools decided by the server itself, which the
config never enumerates and which can change when the server is
upgraded. Requiring teams to list every tool would be busywork that
silently goes stale, and a stale list under-reports delivery — the
failure direction that makes a skill look inert when it was working.

MCP is also better instrumented than either, because its tool names are
self-describing. yacht renders `mcp-server` install steps into the
harness's own configuration under a server name taken from the step's
target, and the harness surfaces those tools under a delimited
namespace — `mcp__<server>__<tool>` for Claude Code, a convention the
tool-claim tutorial and the bundled MCP example already rely on for
preflight expectations. The server name is known from config; the tools
under it announce themselves in the transcript.

## Decision

We will derive MCP delivery from the tool namespace, and report the
server as the unit.

- **The expectation comes from the install step, not a declaration.**
  Each `mcp-server` install step contributes an expectation matching
  its own namespace, built from the step's target. Nothing new is
  configured, and adding a server to a vessel makes it measurable by
  that act alone.
- **Matching is on the delimited namespace, not a bare prefix.** An
  observed call belongs to a server when it matches
  `mcp__<server>__<tool>` with the delimiter intact, so a server named
  `fff` never absorbs calls from one named `fff2`.
- **Delivery is reported per server; the tool breakdown is observed,
  not expected.** A server counts as delivered when any of its tools
  fired, because the treatment under test is the server's availability.
  Which tools fired is read back out of the namespace suffixes and
  reported as description — coverage detail that costs nothing to
  collect and that no one had to predict. A server that exposes twenty
  tools and had one used is delivered, not four percent delivered.
- **Precise expectations remain available and unchanged.** A rigging
  that wants to assert one specific tool keeps doing so with
  `expected_tool_calls`, as the MCP example's preflight already does.
  Namespace delivery answers "was the server used at all"; that is a
  different question from "was this capability exercised", and both
  stay expressible.
- **Unnamespaced harnesses report unmeasured.** The `mcp__` convention
  belongs to Claude Code's rendering. A declared harness whose mapped
  tool calls carry no server namespace yields no MCP expectation and is
  labeled unmeasured rather than guessed at, the same posture ADR 0019
  takes for harnesses that preserve no trajectory.

## Consequences

- The three rigging kinds yacht supports are now all measurable for
  delivery, each by the evidence its own ecosystem already produces:
  a skill's frontmatter name, an extension's declared calls, an MCP
  server's namespace. Nothing about that required a new configuration
  surface.
- Server-level delivery is coarser than per-tool delivery, and
  deliberately so. A team that cares whether a specific capability was
  exercised writes that expectation explicitly; treating unused tools
  as undelivered would report a working server as broken.
- The observed-suffix breakdown makes an MCP server's actual usage
  visible for the first time — which of its tools an agent reaches for,
  and which it ignores. That is useful beyond delivery verdicts, and it
  arrives as a side effect rather than a feature to build.
- Delivery measurement stays honest about its own coverage: harnesses
  that do not namespace MCP tools report unmeasured, and the number of
  ways yacht can be sure keeps being smaller than the number of ways it
  could guess.
