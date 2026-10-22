# smoke-run: yacht run → status → report on the credential-free smoke regatta

## Sub-features

- `yacht validate <config>` accepts the smoke regatta.
- `yacht run <config> --logbook <dir> --workspace .` runs preflight and one task attempt per vessel through the `local-smoke` harness (no Docker, no nix, no model, no credential) and writes a Logbook.
- Preflight evidence per vessel: runtime HOME/XDG isolation, rigging env, isolated rigging state path, agent-prompt tool probe.
- Task attempts per vessel; only the rigged vessel calls `local-smoke` and writes its isolated tool state file.
- `yacht status --logbook <dir>` reads `run-index.json`: lifecycle, readiness, artifact presence, next command.
- `yacht report --logbook <dir>` renders the per-vessel smoke table (status, preflight, attempts, tools, expected, missing, tokens).
- The run leaves the workspace it was given unmodified.

## How to get to it (user POV)

A contributor reads README "Development Smoke", then types, in the repository root:

```sh
uv run yacht validate examples/local-agent-preflight-smoke.toml
uv run yacht run examples/local-agent-preflight-smoke.toml --logbook logbook
uv run yacht status --logbook logbook
uv run yacht report --logbook logbook
```

This is the only no-token path through `run`, `status` and `report`, and every change to preflight, runtimes, attempts, logbook or reports reaches it.

## Driving it with tmux-tty

`scripts/drive-smoke-run` freezes this file, then starts an isolated tmux server whose shell is `env -i` (no inherited credentials) and types the commands below. Each step waits only for the step's end marker (liveness), then captures. Capture file names are `<NN>-<label>.txt` in the evidence dir.

| Step | Typed in the pane | Capture | Observable result |
|---|---|---|---|
| 1 | `env \| grep -Ei 'API_?KEY\|TOKEN\|SECRET\|PASSWORD' \|\| echo none` | `credentials` | no credential variable in the pane shell |
| 2 | `git status --porcelain > $EV/workspace-before.txt` | (none) | baseline of the workspace |
| 3 | `uv run --locked yacht validate examples/local-agent-preflight-smoke.toml` | `validate` | `valid regatta config: local-agent-preflight-smoke`, exit 0 |
| 4 | `uv run --locked yacht run … --logbook $EV/logbook --workspace . --format json > $EV/run-summary.json 2> $EV/run.stderr`, then summary fields and stderr | `run` | exit code, summary status/regatta/course/agent, stderr content |
| 5 | `uv run --locked yacht status --logbook $EV/logbook` | `status` | Status/Lifecycle lines, artifact rows, next command, exit 0 |
| 6 | `uv run --locked yacht report --logbook $EV/logbook` | `report` | per-vessel table, exit 0 |
| 7 | `find $EV/logbook -type f` (paths relative) | `logbook-files` | every artifact the run promised exists on disk |
| 8 | `jq` over `task-attempts/**/*.json` | `attempts` | per-vessel attempt status, tool_calls, tokens |
| 9 | `jq` over `preflight/**/*.json` | `preflight` | per-vessel check names and statuses |
| 10 | `find` + `cat` of `local-tool-state.json` under the logbook runtime dir | `tool-state` | state file only under the rigged vessel, inside the logbook |
| 11 | `git status --porcelain \| diff - $EV/workspace-before.txt` | `workspace` | workspace unchanged by the run |

Evidence dir: `/tmp/verify-yacht/evidence/<run-id>/` (outside the repository tree). Besides the captures it holds `rubric.md`, `rubric.sha256`, `run-summary.json`, `run.stderr`, `workspace-before.txt`, and the full `logbook/`.

## Rubric

```yaml
- id: credential_free_shell
  type: bool
  instructions: Does the credentials capture show the pane shell that ran yacht had no credential-looking environment variable (the capture shows `none` and no variable names)?
  criteria:
    true: capture shows `none` only
    false: any credential-looking variable listed, or capture missing
- id: validate_accepts_config
  type: bool
  instructions: Does the validate capture show the line `valid regatta config: local-agent-preflight-smoke` followed by `validate exit=0`?
  criteria:
    true: valid line present and exit 0
    false: error, traceback, non-zero exit, or capture missing
- id: run_exit_zero
  type: bool
  instructions: Does the run capture show `run exit=0`?
  criteria:
    true: exit code is 0
    false: any other exit code, or capture missing
- id: run_summary_ready
  type: bool
  instructions: Does the run capture show the run summary with status `ready`, regatta `local-agent-preflight-smoke`, course `local-smoke` and agent `local-smoke`?
  criteria:
    true: all four values shown as stated
    false: any value different or absent
- id: run_stderr_clean
  type: bool
  instructions: Does the run capture show the stderr section empty of tracebacks and error lines (an empty section or progress lines only)?
  criteria:
    true: no Traceback, no line beginning `error`
    false: traceback or error line present
- id: status_ready_complete
  type: bool
  instructions: Does the status capture show `Status: ready` and `Lifecycle: complete`, every artifact row marked `[present]` (none `[missing]`), and `status exit=0`?
  criteria:
    true: all three conditions hold
    false: any condition fails or capture missing
- id: report_both_vessels_ready
  type: bool
  instructions: Does the report capture show a table row for each of `local-baseline` and `local-agent-with-tool`, both with status `ready`, preflight `passed` and attempts `measured`, and a header line showing Blocked 0 and Failed 0, with `report exit=0`?
  criteria:
    true: both rows ready/passed/measured, Blocked 0, Failed 0, exit 0
    false: a vessel missing, blocked, failed, or non-zero exit
- id: tool_used_only_by_rigged_vessel
  type: bool
  instructions: Does the report capture show `local-smoke:1` in the tools column for `local-agent-with-tool`, a `-` for tools on `local-baseline`, and `-` in the missing column for both?
  criteria:
    true: rigged vessel used the tool once, baseline used none, nothing expected is missing
    false: tool count differs, baseline shows a tool, or a tool is listed as missing
- id: attempts_completed_per_vessel
  type: bool
  instructions: Does the attempts capture show one completed attempt for each vessel, with `tool_calls` equal to `["local-smoke"]` for `local-agent-with-tool` and `[]` for `local-baseline`?
  criteria:
    true: two completed attempts with the stated tool_calls
    false: an attempt missing, not completed, or tool_calls differ
- id: preflight_checks_passed
  type: bool
  instructions: Does the preflight capture show every listed check with status `passed` for both vessels, including `runtime-home-isolated` for the baseline and `runtime-home-isolated`, `local-tool-mode`, `local-tool-state-isolated` and `local-agent-smoke` for the rigged vessel?
  criteria:
    true: those checks present and all passed
    false: a check absent or with any status other than passed
- id: logbook_artifacts_written
  type: bool
  instructions: Does the logbook-files capture list `run-index.json`, `real-smoke-runbook.json`, `smoke-readiness-report.json`, `smoke-report.txt`, `task-attempt-scorecard.json`, two files under `task-attempts/`, two files under `preflight/`, and transcripts for both vessels?
  criteria:
    true: all listed artifacts present
    false: any missing
- id: tool_state_isolated
  type: bool
  instructions: Does the tool-state capture show a `local-tool-state.json` only under the `local-agent-with-tool` runtime directory inside the logbook (none for `local-baseline`), with content `available` true, `configured` true and `task_id` `local-smoke-1`?
  criteria:
    true: one state file, rigged vessel only, inside the logbook, content as stated
    false: no state file, a state file elsewhere or for the baseline, or content differs
- id: workspace_unchanged
  type: bool
  instructions: Does the workspace capture show the workspace status after the run is identical to before (`workspace unchanged`, no diff lines)?
  criteria:
    true: `workspace unchanged` and no diff lines
    false: diff lines shown or capture missing
```

## Gotchas

- `yacht run` on this config prints its summary on stdout as a long JSON document; the drive redirects it to `run-summary.json` and shows only selected fields, because the capture window is 200 lines.
- `yacht doctor` is not part of the drive: it fails without a Docker daemon and the pinned `yacht/swebench-runner` image, neither of which the smoke path needs.
- The config declares `backend = "host-nix"` with `command_prefix` `nix develop`, but the `local-smoke` harness is in-process and never invokes nix. The pane runs under `env -i` with nix off PATH; the run still succeeds. A future change that really shells out to nix would fail this drive; that is a finding, not a drive defect.
- `uv run --locked` may sync `.venv` (ignored by git) on first use.
- `yacht run` into a non-empty logbook is not exercised; every run gets a fresh evidence dir.
- Tokens are `estimated` (word counts) and duration is `0.0`; the rubric asserts neither.
- `validate` on a missing file raises a raw traceback instead of an error line (observed while interviewing). Not in this rubric; a separate feature if it matters.

## Covers

```yaml
files:
  - src/yacht/cli/commands/regatta.py          # _run_smoke, run dispatch, _validate
  - src/yacht/cli/commands/inspect.py          # _status, _report, smoke branch
  - src/yacht/workflows/real_smoke_eval.py     # run_real_smoke_eval
  - src/yacht/workflows/task_attempt_runner.py # per-vessel attempts
  - src/yacht/harnesses/local_smoke.py         # LocalSmokeAgentAdapter
  - src/yacht/preflight/runner.py              # run_preflight, check execution
  - src/yacht/runtimes/host_nix.py             # _runtime_env isolation
  - src/yacht/runtimes/backend.py              # _create_runtime_dirs
  - src/yacht/reports/smoke_status.py          # build_smoke_status, artifact rows
  - src/yacht/reports/smoke_report.py          # vessel table
  - src/yacht/reports/smoke_readiness.py       # readiness report
  - examples/local-agent-preflight-smoke.toml  # the driven config
  - preflights/local-agent-smoke.md            # agent-prompt check
hashes:
  src/yacht/cli/commands/regatta.py: c8297d28a2bbf75abed389dff75518563d69165dbe0650524486976ad671cbff
  src/yacht/cli/commands/inspect.py: 2bbd2737d3af9c06eeecf1f1344233f6de432e721fa74399aabad90028ee0305
  src/yacht/workflows/real_smoke_eval.py: 1d760caf02f437a806c6396620f711aa22c53883b707d056ec77466e34ba2b5a
  src/yacht/workflows/task_attempt_runner.py: dbb2d3fd80e84b1424af415cdfce6f8337aa6bd226f12a4e60e7d6a5601dc26b
  src/yacht/harnesses/local_smoke.py: 0073379c1a21a165e02663b048593a52588ebe6f4be49dc26a1b2cf0b059b07a
  src/yacht/preflight/runner.py: 7442c2712202419a514bab40d6d30016df5cf7638ee9a4e1cadb34d81cf28dab
  src/yacht/runtimes/host_nix.py: d589bf5611f69de3473c364bdfa55b9ecb4f4f340139ead990af1095cfad5b83
  src/yacht/runtimes/backend.py: cdcaa45bf0096a207086bcb0318030ad6c4eac1f3ce4d11271ff3804d8d98ffb
  src/yacht/reports/smoke_status.py: 5649f39f0436a372c7057aa41c0ea4cbb9c00204c92803a704a5bcdfce3e6ce0
  src/yacht/reports/smoke_report.py: 5725740e7f3b6c61f9949675d3b5d07885c2ca671c7e3d5ed7dcc2c69cd7ed24
  src/yacht/reports/smoke_readiness.py: 6a42cba29e4b1a8e3e8600e363f7ae357eb39f7bc7dd63026558eb315b11e0f6
  examples/local-agent-preflight-smoke.toml: 332fec356590e736244fa86540828c39ced4096979fb081710bb8fd5576c552b
  preflights/local-agent-smoke.md: 47d42098d46d3d4ecc03064b0ed8fe26a463eb581a2a372737a3832ba5433ab3
sync: 151411f40bdc93e8ddeedd2cc33252982d4974ea   # anchor only
```
