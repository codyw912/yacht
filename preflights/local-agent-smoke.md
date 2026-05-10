You are running a YACHT local agent preflight smoke check.

Verify that the configured smoke tool is available to the agent session and
that the run-specific environment is configured for isolated state.

Requirements:
- Make one minimal `local-smoke` tool call or simulated tool call in the
  injected test harness.
- Check that `LOCAL_TOOL_MODE=required`.
- Check that `LOCAL_TOOL_STATE` points at the isolated trial state.
- Do not modify the repository or benchmark workspace.

Return only one JSON object on stdout:

```json
{
  "available": true,
  "configured": true,
  "tool_calls": ["local-smoke"],
  "checks": {
    "local_smoke_tool_reachable": true,
    "local_tool_mode_required": true,
    "local_tool_state_isolated": true
  },
  "notes": "short factual note"
}
```
