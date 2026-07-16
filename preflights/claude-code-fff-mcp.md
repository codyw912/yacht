You are running a YACHT preflight smoke check for the fff MCP integration
in Claude Code.

Verify that the fff MCP server is available in the current session and that
it is configured for the isolated runtime state prepared by YACHT.

Requirements:
- Make one minimal `mcp__fff__fffind` tool call that proves the MCP server
  is reachable.
- Check that the fff MCP server is loaded from this session's configuration.
- Do not modify the repository or benchmark workspace.

Return only one JSON object on stdout:

```json
{
  "available": true,
  "configured": true,
  "tool_calls": ["mcp__fff__fffind"],
  "checks": {
    "fff_mcp_reachable": true,
    "fff_mcp_configured": true
  },
  "notes": "short factual note"
}
```

Set `available` to `false` if the fff MCP server cannot be reached. Set
`configured` to `false` if the server is reachable but does not appear to be
loaded from the trial configuration.
