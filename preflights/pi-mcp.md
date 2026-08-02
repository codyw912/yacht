You are running a YACHT preflight smoke check for the MCP integration in
pi, provided by the pi-mcp-adapter extension.

Verify that the files MCP server is available in the current session and
that it is configured for the isolated runtime state prepared by YACHT.

Requirements:
- Make one minimal `mcp__files_list_allowed_directories` tool call that
  proves the MCP server is reachable.
- Do not modify the repository or benchmark workspace.

Return only one JSON object on stdout:

```json
{
  "available": true,
  "tool_calls": ["mcp__files_list_allowed_directories"],
  "notes": "short factual note"
}
```

Set `available` to `false` if the files MCP server cannot be reached.
