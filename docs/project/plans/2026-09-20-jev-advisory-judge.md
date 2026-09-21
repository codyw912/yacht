# Jev Advisory Judge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sjujperpowers:subagent-driven-development (recommended) or sjujperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable advisory-judge stage to custom-eval verifiers so a cheap System One model (TypeSafe's Jev, or any OpenAI-compatible substitute) can score agent output where a deterministic verifier cannot decide, escalating to a full LLM judge only when confidence is low.

**Architecture:** Jev is a scoring stage inside a custom eval's `tests/test.sh`, not a new `EvaluatorAdapterInterface` kind. A self-contained `tests/judge.sh` helper (digest-pinned with the task) POSTs `state` + typed `questions` to the System One endpoint, reads the verdict + `confidence`, and applies a configurable escalation policy before writing `/logs/verifier/reward.{txt,json}` and a separate advisory `judge.json`.

**Tech Stack:** bash + curl (dependency-free helper), `task.toml` `[verifier] env` with `JUDGE_*` vars, `secretspec.toml` `[scopes.typesafe]`, TypeSafe System One API / OpenAI-compatible endpoint.

**Spec:** `docs/project/specs/2026-09-20-jev-advisory-judge-design.md`

**Source:** plane:YACHT-28

## Global Constraints

- Jev verdict is **advisory** — it feeds the reward, never substitutes for verifier resolution (vision.md:90-92, 156). The verdict lands in `judge.json`, separate from `reward.txt`/`reward.json`.
- `reward.json` must keep a top-level `"reward"` key; the reader (episodes.py:468-472) takes `"reward"` else the sole key only when the dict has exactly one. Never fold the Jev verdict into `reward.json` without a `"reward"` key.
- Record the response's concrete `model` (e.g. `jev-1.13.0`) in `judge.json`; comparable runs pin an explicit model version, not `jev-latest`.
- `verify_between = true` runs `tests/test.sh` directly and ignores `[verifier] env` (custom-evals.md:219) — Jev judging under `verify_between` is a named edge case, not silently supported.
- `[verifier] timeout_sec` must cover the Jev call plus any escalation; the helper sets its own `request_timeout_sec` and writes the `on_error` fallback rather than letting the verifier be killed.
- `TYPESAFE_API_KEY` is provisioned via Iron Proxy (`api.typesafe.ai` route live). **Settled by probe:** `required_secrets` does NOT reach the verifier — the key must be set explicitly in `[verifier] env` (which Harbor interpolates in the launcher process, where `required_secrets` does deliver it). Both are needed.

---

### Task 1: Probe — does `required_secrets` reach the verifier?

Settle the open assumption before building the helper on it.

**Files:**
- Create: `examples/custom-evals/jev-probe-task/task.toml`
- Create: `examples/custom-evals/jev-probe-task/tests/test.sh`
- Create: `examples/custom-evals/jev-probe-task/environment/Dockerfile`

**Interfaces:**
- Produces: a documented answer to "does `required_secrets`/`secret_env` reach `tests/test.sh`, or must the key go in `[verifier] env`?" — recorded as a comment in the probe task and reported back.

- [ ] **Step 1: Write the probe task**

`examples/custom-evals/jev-probe-task/task.toml`:

```toml
[metadata]
author = "yacht"
description = "Probe: does required_secrets reach the verifier env?"
difficulty = "easy"

[verifier]
timeout_sec = 30.0
# Deliberately no [verifier] env — testing whether required_secrets leaks through.

[agent]
timeout_sec = 60.0
```

`examples/custom-evals/jev-probe-task/tests/test.sh`:

```bash
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
# Presence check only — never echo the key value into trial evidence.
if [ -n "${TYPESAFE_API_KEY:-}" ]; then
  echo "TYPESAFE_API_KEY=SET" > /logs/verifier/probe.txt
else
  echo "TYPESAFE_API_KEY=UNSET" > /logs/verifier/probe.txt
fi
echo 1 > /logs/verifier/reward.txt
```

`examples/custom-evals/jev-probe-task/environment/Dockerfile`: minimal `FROM debian:bookworm-slim` + `bash`.

- [ ] **Step 2: Run the probe**

Run a custom eval against the probe task with `required_secrets = ["typesafe"]` on the runtime and `secretspec run --scope typesafe`. Inspect `/logs/verifier/probe.txt` in the trial's evidence.

- [ ] **Step 3: Record the answer**

If `TYPESAFE_API_KEY` is SET in the verifier → `required_secrets` reaches the verifier; the helper reads it directly. If UNSET → the key must be set explicitly in `[verifier] env`; document that. Record the result as a comment in `task.toml` and report it back.

- [ ] **Step 4: Commit**

```bash
jj commit examples/custom-evals/jev-probe-task -m "Add verifier-env probe task for Jev"
```

---

### Task 2: The `judge.sh` helper

A dependency-free `curl` helper a custom-eval verifier drops into `tests/` and calls. Reads `JUDGE_*` config from `[verifier] env` vars the task sets, POSTs to the System One endpoint, applies the escalation policy, writes `reward` + `judge.json`.

**Files:**
- Create: `examples/custom-evals/jev-task/tests/judge.sh`
- Create: `examples/custom-evals/jev-task/tests/test.sh`
- Create: `examples/custom-evals/jev-task/task.toml`
- Create: `examples/custom-evals/jev-task/environment/Dockerfile`

**Interfaces:**
- Consumes: env vars `JUDGE_BACKEND`, `JUDGE_BASE_URL`, `JUDGE_MODEL`, `JUDGE_API_KEY_ENV`, `JUDGE_CONFIDENCE_THRESHOLD`, `JUDGE_ON_LOW_CONFIDENCE`, `JUDGE_MODEL_ESCALATION`, `JUDGE_BASE_URL_ESCALATION`, `JUDGE_API_KEY_ENV_ESCALATION`, `JUDGE_REQUEST_TIMEOUT_SEC`, `JUDGE_ON_ERROR`, `JUDGE_STATE_FILE`, `JUDGE_QUESTION_FILE`.
- Produces: writes `/logs/verifier/reward.txt` (or absent per `on_error`), `/logs/verifier/judge.json` `{backend, model, question, answer, confidence, escalated, escalation_verdict}`. Callable as `tests/judge.sh` from `test.sh`.

- [ ] **Step 1: Write the helper**

`judge.sh` reads config from env (with defaults matching the spec), builds the System One request body from `JUDGE_STATE_FILE` + `JUDGE_QUESTION_FILE`, POSTs via `curl` with `request_timeout_sec`, parses the answer + `confidence` with `python3`/`jq` fallback, applies `on_low_confidence`/`on_error`, writes `reward.txt` + `judge.json`. Backend `openai-compat` maps the same request to an OpenAI-compatible `/chat/completions` shape for self-hosted substitutes.

- [ ] **Step 2: Write the example task**

`test.sh` calls `judge.sh` with a Noul question ("does the output satisfy criterion X"); `task.toml` sets `[verifier] env` with `JUDGE_*` vars + the API key; `environment/Dockerfile` provides `curl` + `python3`.

- [ ] **Step 3: Test the helper offline**

Run `judge.sh` against a stub `base_url` (a local `python3 -m http.server` returning a canned System One response) to verify request shape, confidence parsing, escalation branching, and `judge.json` output — no live API call.

- [ ] **Step 4: Commit**

```bash
jj commit examples/custom-evals/jev-task -m "Add Jev advisory judge helper and example task"
```

---

### Task 3: secretspec scope + docs

**Files:**
- Modify: `secretspec.toml` (add `[scopes.typesafe]`)
- Modify: `docs/reference/custom-evals.md` (advisory-judging section)

- [ ] **Step 1: Add the scope**

```toml
[scopes.typesafe]
secrets = ["TYPESAFE_API_KEY"]
```

- [ ] **Step 2: Document advisory judging**

Add a "Advisory judging" section to `custom-evals.md`: the seam (scoring stage in `test.sh`, not an evaluator adapter), the `[verifier] env` `JUDGE_*` config knobs, the `verify_between` caveat, the `judge.json` evidence contract, the `reward.json` `"reward"`-key caveat, and the model-pinning note.

- [ ] **Step 3: Commit**

```bash
jj commit secretspec.toml docs/reference/custom-evals.md -m "Add typesafe scope and advisory-judging docs"
```

---

## Self-review notes

- Spec coverage: seam (Task 2), helper delivery (Task 2), escalation policy (Task 2), secrets/env (Tasks 1+3), edge cases — `verify_between`, timeout, base-URL override (Task 2 + docs), evidence contract (Task 2 + docs), reproducibility caveats (docs). Probe task = Task 1.
- Open assumption (verifier env) is Task 1's deliverable; the helper's env-var contract is written to work under either outcome.
- No placeholders; each task ends in a testable deliverable.
