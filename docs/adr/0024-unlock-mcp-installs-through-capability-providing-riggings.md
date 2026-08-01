# ADR 0024: Unlock MCP Installs Through Capability-Providing Riggings

## Status

Accepted

## Context

ADR 0022 made MCP servers measurable for delivery, and the capability
gate keeps that measurement honest by refusing an `mcp-server` install
step on any harness without MCP support. Today that gate is keyed on
the harness name alone: Claude Code supports MCP, everything else is
refused before tokens are spent.

Pi breaks the key. MCP support is explicitly not shipping in pi's base
package — there is no official pi MCP support at all; extensions are
the only route, and more than one such extension can exist.
`pi-mcp-adapter`, installed from npm and loaded through pi's package
manifest, is one of them and the concrete example throughout this
document. The capability is real, but it is a property of the
*rigging composition*, not of the harness: a stock pi vessel cannot
carry an MCP server, and the same vessel with an adapter rigged in
can. yacht already runs stock-versus-extended comparisons as its
original use case (the fff examples); what it cannot yet express is an
extension that changes which install methods the vessel accepts.

The adapter also decides whether delivery stays measurable. Its default
proxy mode funnels every server through a single `mcp` tool, which
keeps the agent's context small but makes per-server attribution from
tool names impossible. Its `directTools` mode with
`toolPrefix = "mcp"` produces exactly the delimited
`mcp__<server>__<tool>` convention ADR 0022 already matches. Both are
settings in the same file the servers are configured in
(`<pi agent dir>/mcp.json`, inside the trial's isolated home) — so the
choice between an observable treatment and an unobservable one is a
line of configuration yacht is already in a position to write.

## Decision

We will let a rigged tool provide an install capability its harness
lacks, and configure the treatment to be observable as part of
providing it.

- **A tool capability may declare that it provides an install method
  for a named harness.** The declaration lives on the `[tools.<name>]`
  entry (e.g. the adapter declares it provides `mcp-server` for `pi`),
  and the capability gate accepts an `mcp-server` step for a vessel
  when the runtime harness supports it natively or a tool rigged on
  that same vessel provides it for that harness. Everything else keeps
  refusing before tokens are spent.
- **The provider installs by ordinary steps and is pinned like any
  rigging.** The adapter itself arrives via existing install methods
  with a version-pinned target; nothing about provision exempts it
  from the determinism rules.
- **yacht renders the MCP configuration into the provider's own file,
  in the trial home, with observability pinned — and that rendering is
  per-provider knowledge yacht ships.** A provider is supported the
  way a harness is supported: yacht knows its config format, its
  file's place in the trial home, and the settings that make delivery
  measurable, or the provider cannot be declared. For pi-mcp-adapter,
  the first supported provider, that is one JSON document carrying
  both the declared servers and the adapter settings, with
  `directTools` on and `toolPrefix` set to the delimited `mcp`
  convention. The namespace ADR 0022 matches becomes a configured fact
  of the rig, not a hope about defaults — the same posture as pinning
  a version.
- **Expectation derivation keys on the guarantee, not the harness
  list.** MCP delivery expectations are emitted when the harness
  namespaces natively (Claude Code) or when the vessel's rigging
  includes a provider whose rendered configuration pins the delimited
  convention. A provider that cannot guarantee the convention yields
  no expectation and the server reports unmeasured — never guessed at.
- **Liveness is proven by the agent, not the config.** The adapter's
  servers are lazy: they connect on first tool call, so a
  config-presence check proves rendering, not a working server. The
  agent-prompt preflight with `expect_tool_calls` remains the liveness
  gate, exactly as the Claude Code MCP example uses it.

## Consequences

- Stock-versus-extended comparisons extend to MCP on pi: baseline pi
  against pi with the adapter and a server, with delivery evidence on
  the treatment side. The treatment is honestly a composition — the
  adapter plus the server — and the comparison measures the
  composition. A team that wants the server's effect isolated on pi
  puts the adapter on both vessels and rigs only the server on one.
- The capability gate's refusal message stops being the last word for
  pi. It remains the last word for any harness with neither native
  support nor a declared provider, which is the honest boundary: the
  gate refuses what cannot work rather than what has not been tried.
- yacht writing the adapter's settings is a deliberate intrusion into
  treatment configuration, and a narrow one: it pins exactly the
  settings that determine whether evidence exists, the way it already
  pins versions so provenance exists. A run whose operator wants proxy
  mode is measuring context economics, not delivery, and can declare
  no expectation by leaving provision undeclared.
- Provision is declared per harness, so a future adapter for another
  harness reuses the mechanism without widening it: the gate learns
  nothing about harnesses, only about declarations.
- The mechanism privileges no particular extension. Pi has no official
  MCP support, so any MCP-providing extension enters the same way:
  yacht ships its rendering and namespace guarantee, and the
  declaration does the rest. pi-mcp-adapter is the first supported
  provider, not the definition of one.
- The number of ways yacht can be sure stays smaller than the number
  of ways it could guess: no provider declaration, no expectation; no
  namespace guarantee, no delivery verdict.
