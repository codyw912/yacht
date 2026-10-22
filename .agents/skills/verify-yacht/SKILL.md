---
name: verify-yacht
description: Drive the real `yacht` CLI (YACHT, the coding-harness evaluation control plane) through its credential-free smoke path (validate, run, status, report) in an isolated tmux session and leave evidence plus a frozen rubric. Use when verifying a change to yacht's run pipeline, preflight, runtimes, task attempts, logbook, or smoke reports.
---

# verify-yacht

Surface: **CLI** (`yacht`, installed by `uv sync --locked` into `.venv`), driven with `scripts/lib/tmux-tty.sh`. Other surfaces exist and are not driven: `yacht serve` (read-only local dashboard, a web UI: no driver in this pack), Docker/Harbor-backed courses (need a Docker daemon, images, and a provider credential).

One feature is mapped: [`smoke-run`](features/smoke-run.md) (index: [features/README.md](features/README.md)). It uses `examples/local-agent-preflight-smoke.toml`, whose `local-smoke` harness is in-process and needs no credential, Docker, or network.

## Launch

```sh
.agents/skills/verify-yacht/scripts/launch
```

yacht is short-lived, so launch means build once: `uv sync --locked`, then `yacht validate` on the smoke config. Ready = last line `ready: yacht built from <root>`. Each drive starts its own tmux session.

## Doctor

```sh
.agents/skills/verify-yacht/scripts/doctor
```

Read-only. Checks tmux, uv, git, repo identity, smoke config and preflight prompt present, `.venv/bin/yacht` present, `uv.lock` current, `/tmp` writable. Reports credential-looking variables in the calling shell (the drive strips them with `env -i`; it never reads them). Non-zero exit prints `fix:` lines. Do not use `yacht doctor` here: it needs Docker and the SWE-bench runner image, which this path does not use.

## Drive

```sh
.agents/skills/verify-yacht/scripts/drive-smoke-run
```

Freezes `features/smoke-run.md` into the evidence dir, starts a tmux session whose shell is `env -i HOME PATH`, types the validate/run/status/report commands plus read-only inspections of the Logbook, waits only for each command's end marker, captures after each. The last line printed is the evidence dir. Steps and expected observations: the feature file.

Isolation: every run has its own run id, tmux server (`cstack-verify-yacht-<run-id>`), Logbook (inside the evidence dir), and handle file. Two drives can run side by side.

## Evidence

`/tmp/verify-yacht/evidence/<run-id>/` (outside the repository tree): numbered captures `NN-<label>.txt`, `rubric.md` and `rubric.sha256` (frozen before the drive), `run-summary.json`, `run.stderr`, `workspace-before.txt`, `workspace-after.txt`, and the complete `logbook/`. Judging is `verify`'s job; this skill only produces and describes the evidence.

## Cleanup

```sh
.agents/skills/verify-yacht/scripts/cleanup
```

Stops every run recorded in `/tmp/verify-yacht/handles/<run-id>.session` by session handle, removes the handles, never touches evidence. Safe to run twice. Run it after every drive, including failed ones; the drive records its handle before starting tmux.

## Helpers

| Script | Invocation (no arguments) |
|---|---|
| `scripts/doctor` | `.agents/skills/verify-yacht/scripts/doctor` |
| `scripts/launch` | `.agents/skills/verify-yacht/scripts/launch` |
| `scripts/drive-smoke-run` | `.agents/skills/verify-yacht/scripts/drive-smoke-run` |
| `scripts/cleanup` | `.agents/skills/verify-yacht/scripts/cleanup` |
| `scripts/lib/tmux-tty.sh` | sourced by the drive and cleanup; copied unchanged from the create-verification-skill driver |

## Proof run

Generated on Linux x64, tmux 3.6a, uv 0.11.21, base commit `151411f40bdc93e8ddeedd2cc33252982d4974ea` (tree `30cc0a3fa553712b9eb7e77e8ae9f8451ed5e29e`). Sequence run from the repo root:

```sh
.agents/skills/verify-yacht/scripts/doctor            # exit 0
.agents/skills/verify-yacht/scripts/launch            # exit 0
.agents/skills/verify-yacht/scripts/drive-smoke-run   # exit 0
.agents/skills/verify-yacht/scripts/cleanup           # exit 0, twice
```

Evidence: `/tmp/verify-yacht/evidence/20261022-092821-1024964` (captures 01-10, frozen rubric, Logbook). After cleanup the evidence remained and `tmux -L cstack-verify-yacht-20261022-092821-1024964 has-session` failed.

The first attempt failed twice and was fixed before this run: `doctor` exited 2 on an empty handles glob under `pipefail`, and the drive waited for the literal `verify$ ` which tmux trims. The evidence was not judged during generation.
