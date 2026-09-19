# ADR 0026: Allow Opt-In Advisors in Controlled OMP Execution

## Status

Accepted

## Context

Controlled OMP execution (the `[execution]` controller, shipped in the
bounded-OMP runtime) disables advisors outright: `advisor.enabled` is
hardcoded `false` in `CONTROLLED_SETTINGS` and applied after
`loadIsolated`, so no rigging or task can turn one on. That was the
right default — an advisor is unbudgeted side inference, and a
cost-comparison trial that silently runs one is measuring the wrong
thing.

The advisor-gating evaluation needs the opposite: a controlled trial
*with* an advisor, so it can measure how much the advisor spends and
whether gating that spend changes review quality. The eval's design
(`yacht-evals/docs/advisor-gating-eval.md`) asks for two things: a way
to run an advisor inside controlled execution, and a way to see its
token/cost usage separately from the primary's.

Three constraints shape the design:

- **Advisor spend is a separate agent.** The admission gate hooks the
  primary's `addBeforeModelCall`; advisor model calls run on a different
  `Agent`'s stream and are not counted or capped by it. The eval only
  needs advisor usage *reported*, not capped — capping is out of scope.
- **The advisor roster must be controller-supplied.** `createAgentSession`
  always runs `discoverAdvisorConfigs(cwd, agentDir)`, which walks the
  project `cwd` for `WATCHDOG.yml`. Under controlled execution the
  evaluated agent shares that workspace and could write a `WATCHDOG.yml`
  to replace the advisor roster, instructions, model, or tools at the
  next runtime rebuild. The roster must come from the driver, not the
  filesystem.
- **The advisor's tool set must be explicit and bounded.** An advisor that
  could reach the model-spawning tools (`task`, `eval`, `browser`) the
  controlled primary is denied would break the side-inference boundary, and
  `bash`/`edit`/`write` on the evaluated workspace would let it act rather
  than observe. An opted-in advisor must get a restricted, recorded tool
  set — the driver defaults it to `read`/`grep`/`glob` and rejects any
  model-spawning tool.

## Decision

Controlled OMP execution gains an **opt-in advisor arm**, off by
default and configured entirely by the controller.

### Init-time opt-in

The `init` driver command accepts an optional `advisor` field:

```json
{ "type": "init", "model": "<primary>", "deadline_ms": 900000,
  "advisor": { "model": "<provider>/<id>[:<level>]",
               "tools": ["read", "grep", "glob"],
               "instructions": "..." } }
```

When present, the driver:

1. Holds `advisor.enabled` off through `createAgentSession` so the SDK does
   not build a legacy `{name: "default"}` advisor from the `advisor` role
   before the controller's roster is installed. An explicit advisor `model`
   is required in the init payload — the per-advisor `config.model` resolves
   directly via `resolveModelOverride` (it never consults `modelRoles.advisor`
   or the `slow` chain, which only fire when `config.model` is unset), so a
   missing model is a contract error, not a silent fallback.
2. After the session is built, calls
   `session.applyAdvisorConfigs([{name, model, tools, instructions}])` to
   install the controller-supplied roster (stored only while disabled), then
   `session.setAdvisorEnabled(true)` to build the runtime from that roster —
   enabling first would construct the legacy default advisor and tear it down.
   If `discoverAdvisorConfigs` located any project-level `WATCHDOG.yml`, init
   refuses — an agent-writable advisor definition is an infrastructure error,
   not a silent override. The recorded `advisor.enabled` setting is then
   synced to `true` so the reported policy matches the live runtime.
3. Asserts the resolved advisor model equals the requested selector,
   mirroring the primary's `model mismatch` check. "Advisor enabled but
   no model resolved" (`isAdvisorEnabled() && !isAdvisorActive()`) is an
   infrastructure error, not a zero-cost arm.

Before each settle is captured the driver drains the advisor:
`prepareForHeadlessAdvisorDrain()` keeps a late `blocker` note from waking
the primary after its terminal answer (it is preserved as a card instead),
and `waitForAdvisorCatchup()` lets the in-flight review land so the reported
spend/status is complete. A drain that times out or fails marks the advisor
`error` in the settle rather than reporting a partial cost as clean.

When `advisor` is absent, behavior is unchanged: `advisor.enabled`
stays `false` and no advisor runtime is built.

### Reported, not capped

Advisor usage is reported in the settle frame and the trial summary as
a **separate** block, never folded into the primary's `usage`/`cost_usd`
(downstream scorecards read those as primary spend). The block carries,
per advisor: `name`, `status` (`running | paused | quota_exhausted |
error | no_model`), resolved `model`, `tokens`, `cost`, and `messages`.

`status` is the load-bearing field: an advisor that hit a provider
overflow or quota limit and died mid-trial reports `error` /
`quota_exhausted`, distinguishing "advisor ran and spent X" from
"advisor died and looks free." `getAdvisorCost()` is the monotonic
ledger; the per-advisor `tokens` sum reads the advisor's *retained*
context and can drop when context maintenance trims it, so cost is the
authoritative cumulative figure and tokens are a per-settle snapshot.

### Guard the default

`advisor.enabled` joins `SIDE_INFERENCE_GUARDS`, asserted against the
trial's *expected* value (off unless the init opted in). A drifted
settings source can no more silently enable an advisor than it can
re-open memory or autolearn.

## Consequences

- The advisor-gating eval can run controlled trials with an advisor and
  read its spend from the summary, satisfying the eval doc's option (b).
- The controlled-execution invariant is restated honestly: it becomes
  "no *unrecorded* side inference," not "no unbudgeted side inference."
  An advisor only runs when the controller explicitly arms it, with a
  pinned model and a restricted, recorded tool set — but its spend is
  uncapped and that relaxation is now explicit, not implied.
- The advisor's *prompt inputs* still come from workspace discovery:
  `advisorWatchdogPrompt` (from `WATCHDOG.md`) and `advisorContextPrompt`
  (from `AGENTS.md` and friends) are injected by `createAgentSession`
  independently of the roster. That is agent-writable, so the summary
  records which watchdog/context files were discovered (or their
  digests) — a planted `WATCHDOG.md` is visible evidence, not a silent
  treatment change.
- `docs/reference/custom-evals.md`'s "advisors disabled" statement is
  updated to describe the opt-in.
- Advisor spend remains *uncapped* — the admission gate does not extend
  to it. A runaway advisor is a real cost; the eval accepts this because
  it is measuring advisor cost, not bounding it. A future change could
  add a separate advisor budget if an eval needs one.
