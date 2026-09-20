# Jev as an advisory judge for evals

**Outcome:** plane:YACHT-28

## Intent

Use TypeSafe's Jev — a hosted "System One" model — as an advisory judge for
custom evals: a cheap, fast classifier for pass/fail where a deterministic
verifier cannot decide, escalating to a full LLM judge only when Jev's own
confidence is low. The verdict stays advisory — it feeds the reward, it is not
ground truth (vision.md:90-92, 156).

## What Jev is

Jev is TypeSafe's flagship model, accessed via HTTP API or the `typesafe-sdk`
Python/JS SDKs. You send a `state` plus typed `questions`; it returns structured
answers — no text generation, no parsing. Three primitives:

- **Choice** — pick from options → `choice`, `probabilities`, `confidence`
- **Score** — position on a rubric → `score`, `legend`, `probabilities`, `confidence`
- **Noul** — yes/no → `noul` (0–1)

`confidence` is a first-class output derived from the probability spread — the
escalation policy thresholds on it. Endpoint: `POST
https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer $TYPESAFE_API_KEY`.
Docs: https://docs.typesafe.ai.

## The seam

Jev is **not** a new `EvaluatorAdapterInterface` kind. `_EVALUATOR_ADAPTERS`
(courses/registry.py:699-721) is keyed 1:1 with course kinds and each entry only
reads a per-benchmark native grading report. Jev is a **scoring stage inside a
custom eval's verifier** (`tests/test.sh`): it produces evidence the verifier
consumes when writing `/logs/verifier/reward.{txt,json}`. It feeds the report;
it is not the report reader.

## How it runs

The verifier (`tests/test.sh`) executes inside the task's user-authored
environment image. Jev integration is a **self-contained helper shipped with the
task** under `tests/` — digest-pinned with the task, no dependency on Yacht's
release or on Python/`typesafe-sdk` being in the image. The helper is a
dependency-free `curl` POST to the System One endpoint (or a `python3` +
`typesafe_sdk` snippet when the image already has them), so it runs in any task
container that has `curl` or `python3`.

Flow inside `test.sh`:

1. Build `state` from the agent's output — the file(s) under test, the captures
   under `/logs/verifier/yacht-execution/`, or a task-defined subset.
2. Ask a typed question — Noul ("does the output satisfy criterion X") for a
   clean verdict, Score for rubric-graded quality, Choice for pass/fail/unclear.
3. Read the answer + `confidence`.
4. Apply the escalation policy (below) → write `reward.{txt,json}` and a
   `judge.json` evidence file.

## Configurable escalation policy

Per the operator's note, the escalation is user-configurable, not hardcoded. The
verifier reads a policy from `task.toml` `[verifier] env` as `JUDGE_*` vars
(the only channel that reaches `tests/test.sh`):

```toml
[verifier]
timeout_sec = 120.0          # must cover Jev + any escalation call

[verifier.env]
# Which backend the judge calls. Default "typesafe"; "openai-compat" points at
# any OpenAI-compatible endpoint for self-hosted/open-weight substitutes.
JUDGE_BACKEND = "typesafe"
JUDGE_BASE_URL = "https://api.typesafe.ai/v1/systemone"   # overridable
JUDGE_MODEL = "jev-latest"
JUDGE_API_KEY_ENV = "TYPESAFE_API_KEY"                     # env var the helper reads

# Escalation policy
JUDGE_CONFIDENCE_THRESHOLD = "0.5"   # below this, escalate
JUDGE_ON_LOW_CONFIDENCE = "llm-judge"   # llm-judge | human-review | advisory-only
JUDGE_MODEL_ESCALATION = "xai-oauth/grok-4.6" # model for llm-judge escalation
JUDGE_BASE_URL_ESCALATION = "http://omp-subscriptions.home.lan:4000/v1"
JUDGE_API_KEY_ENV_ESCALATION = "OPENAI_API_KEY"
JUDGE_REQUEST_TIMEOUT_SEC = "20"
JUDGE_ON_ERROR = "unresolved"      # unresolved | zero | advisory-only
```

- **`on_low_confidence = "llm-judge"`** — call a full LLM (Grok/Claude via the
  subscription gateway, or any OpenAI-compatible endpoint) for a second opinion.
- **`"human-review"`** — leave reward unresolved, flag the trial for a human.
- **`"advisory-only"`** — record the verdict as evidence but never decide the
  reward; a deterministic verifier still owns resolution.
- **`on_error`** — what the helper writes when Jev or the escalation call fails
  or times out: `unresolved` (no reward written, trial flagged), `zero`
  (reward 0), or `advisory-only` (record the failure, don't decide).

## Secrets and env

`TYPESAFE_API_KEY` is already provisioned via Iron Proxy (`api.typesafe.ai`
route is live). Two delivery paths, one open assumption:

- **`secretspec.toml`** gets a `[scopes.typesafe]` block declaring
  `TYPESAFE_API_KEY`, so `secretspec run --scope typesafe` resolves it.
- **Reaching `tests/test.sh`:** the verifier reads `[verifier] env` from
  `task.toml`. **Settled by probe:** `secret_env`/`required_secrets` does NOT
  reach the verifier's environment — the probe task's `test.sh` saw
  `TYPESAFE_API_KEY` unset even with the secret declared. The key must be set
  explicitly in `[verifier] env` (which Harbor interpolates in the launcher
  process, where `required_secrets` does deliver it). Both are needed:
  `required_secrets` gets the value to the launcher; `[verifier] env` maps it
  into the verifier.

## Edge cases baked in

- **`verify_between = true`:** the inter-episode exec runs `tests/test.sh`
  directly and **ignores `[verifier] env`** (custom-evals.md:219). If the key is
  delivered via `[verifier] env`, mid-relay verification calls Jev without a key
  and fails/scores 0 while the final verifier works. **Decision:** either pass
  the key by a route that survives `verify_between` (agent env, or a file the
  task image ships), or document that Jev judging is incompatible with
  `verify_between = true` and reject the combination at render time.
- **Verifier timeout:** `[verifier] timeout_sec` defaults to 60s; a Jev call
  plus an LLM-judge escalation can exceed that. The helper sets its own
  `request_timeout_sec` per call and writes the `on_error` fallback rather than
  letting the verifier be killed and lose the reward entirely.
- **Base-URL override:** `backend = "openai-compat"` + `base_url` lets a user
  substitute a self-hosted/open-weight model for Jev without changing the
  helper's contract — same `state` + `questions` in, same verdict + confidence
  out.

## Evidence contract

The Jev verdict lands in its own advisory block, separate from the reward, so
the scorecard can show "advisory: pass (0.9)" distinct from "resolved: 1.0":

```
/logs/verifier/
├── reward.txt          # the grading truth (or absent if unresolved)
├── reward.json
└── judge.json          # advisory: {backend, model, question, answer,
                        #            confidence, escalated, escalation_verdict}
```

`judge.json` is advisory evidence — it never substitutes for verifier
resolution, mirroring how the advisor arm's spend stays out of primary
usage/cost_usd.

Two reproducibility caveats:

- **`reward.json` shape:** the reward reader (episodes.py:468-472, mirroring
  terminal_bench's `_trial_reward`) takes the `"reward"` key, else the sole key
  only when the dict has exactly one. A verifier writing `{"reward": 1,
  "judge_confidence": 0.9}` is fine, but writing the Jev verdict into
  `reward.json` without a `"reward"` key silently yields `None`. Keep the
  advisory verdict in a separate `judge.json` — never fold it into `reward.json`.
- **Model pinning:** the content digest (task_directory.py:9-30) pins task
  files, but a Jev verdict from `model = "jev-latest"` is not pinned — the API
  returns a concrete version (e.g. `jev-1.13.0`) and identical digests can then
  score differently across runs. Record the response's `model` in `judge.json`,
  and note that comparable runs should pin an explicit model version, not the
  alias.

## What Yacht core ships

1. `[scopes.typesafe]` in `secretspec.toml` declaring `TYPESAFE_API_KEY`.
2. A `tests/judge.sh` helper snippet + a documented `[verifier] env` config
   block for custom-eval tasks.
3. A `docs/reference/custom-evals.md` section on advisory judging: the seam,
   the config knobs, the `verify_between` caveat, and the evidence contract.
4. The probe task above (settled: `required_secrets` does not reach the
   verifier; `[verifier] env` is required).

## Open questions

- For `verify_between` tasks, is Jev judging rejected at render, or is the key
  delivered by a route that survives mid-relay execs?
- Which primitive is the default for pass/fail — Noul or Choice?
- Does the escalation judge need its own secret scope, or does it reuse the
  agent's provider key?
