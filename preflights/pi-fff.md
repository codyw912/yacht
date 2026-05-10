You are running a YACHT preflight smoke check for the Pi fff integration.

Verify that the fff tool is available from the current agent session and that
it is configured for the isolated runtime state prepared by YACHT.

Requirements:
- Make one minimal fff tool call that proves the tool is reachable.
- Check that fff is configured for this run, including `PI_FFF_MODE=required`.
- Check that fff state paths are isolated to the trial runtime state when those
  paths are visible to you.
- Do not modify the repository or benchmark workspace.

Return only one JSON object on stdout:

```json
{
  "available": true,
  "configured": true,
  "tool_calls": ["fff"],
  "checks": {
    "fff_tool_reachable": true,
    "pi_fff_mode_required": true,
    "fff_state_isolated": true
  },
  "notes": "short factual note"
}
```

Set `available` to `false` if the fff tool cannot be reached. Set
`configured` to `false` if the tool is reachable but the required mode or
isolated state configuration cannot be confirmed.
