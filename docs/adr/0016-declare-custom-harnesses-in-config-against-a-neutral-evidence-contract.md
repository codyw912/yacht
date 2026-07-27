# ADR 0016: Declare Custom Harnesses in Config Against a Neutral Evidence Contract

## Status

Accepted; evidence emission amended by ADR 0017 (harnesses no
longer need to emit the wire format — declared field-mapping over
harness-native output is the primary custom path).

## Context

YACHT evaluates harnesses, but the set of harnesses it can drive is
closed: `src/yacht/harnesses/registry.py` resolves adapters from a
hardcoded in-module dict, and adding a harness means editing YACHT's
source. ADR 0015 opened the task side to user-authored content; there is
no analogous path for user-authored harnesses. The first real consumer
is waiting on one: yach, an open-source Rust coding harness, wants to
run under YACHT without an in-tree adapter — deliberately, so the
extensibility story gets exercised by an outsider before it is declared
supported.

The built-in adapters show what an adapter actually contributes. The
launch mechanics are generic: argv comes from the runtime instance
(`command_prefix + runtime.command`), the prompt is appended as the
final argument, the subprocess runs in the task workdir with filtered
env plus injected secrets, and the launcher writes the transcript. What
is harness-specific is evidence extraction: the Pi and Claude Code
adapters each parse their harness's native stdout stream to recover the
response text, tool calls, token usage, and cost, and fall back to raw
stdout and a chars-based token estimate when parsing fails. Bespoke
in-YACHT parsing per harness cannot scale to harnesses YACHT does not
ship — and the estimate fallback already lets approximated numbers mix
silently with reported ones.

Provisioning, by contrast, needs no new machinery: the existing runtime
backends already deliver arbitrary binaries — a container image bakes
the harness in, a host-nix flake provides it — and agent-prompt
preflight proves the harness runs end to end before tokens are spent.
The gap is declaration and evidence, not delivery.

## Decision

We will let configs declare harnesses, and define a neutral evidence
contract that declared harnesses emit instead of YACHT parsing their
native output.

- **Harnesses become declarable in config.** A `[harnesses.<name>]`
  table registers a custom harness; runtimes reference it by name
  exactly as they reference built-ins. The declaration carries what the
  built-in adapters hardcode: how the prompt is passed (`argument` —
  appended as the final argv element, the built-in convention — or
  `stdin`) and where evidence comes from (`stdout` — the final line of
  output — or `file` — a path YACHT provides in the
  `YACHT_EVIDENCE_PATH` environment variable). Built-in names stay
  reserved; a config cannot shadow them.
- **The evidence contract is a versioned schema, not parsing.**
  `yacht.harness-evidence.v1` is a JSON document the harness emits:
  response text, tool calls (with per-tool counts), token usage
  (input/output, cache read/write where known), cost when known, the
  resolved model when known, and a free-form extras object. YACHT
  validates it like any other schema. The dependency points the right
  way: YACHT defines the contract once; any harness that wants to be
  measured targets it.
- **The custom path never estimates.** Missing or invalid evidence
  fails the attempt loudly — a declared harness that does not emit the
  contract is a broken integration, not a degraded measurement. The
  built-in adapters keep their native parsing, but their estimate
  fallback stops being silent: metrics record whether usage was
  reported by the harness or estimated by YACHT, so cross-harness
  comparisons never mix the two without saying so.
- **Everything else is the existing contract, now documented.** Launch
  semantics (one autonomous prompt-to-completion session in the task
  workdir, no interactive approvals), exit-code meaning (nonzero is a
  failed attempt, recorded as evidence), transcript ownership (YACHT's
  launcher writes it; the harness need not), and env filtering are
  already uniform across adapters — a custom-harness reference page
  states them so integrators stop reverse-engineering `pi.py`.
- **Declared harnesses reach both execution paths; delivery is
  sequenced.** The same `[harnesses.<name>]` declaration serves
  yacht-run rollouts (SWE-bench, LiveCodeBench) and native-rollout
  Harbor courses (Terminal-Bench, Aider Polyglot, custom evals) — both
  are part of this decision, with yacht-run landing first because it
  needs no in-container installation. For the Harbor path, a generic
  declared-harness agent joins YACHT's Harbor agent classes
  (ADR 0012): it installs the harness inside the task container from
  the declaration's install steps and runs it under the same launch
  semantics. The plumbing already exists — Harbor's agent `kwargs`
  passthrough, which carries `rigging_steps` today, carries the
  declaration.
- **In-container installation is pinned and checksummed.** The
  declaration's install section names how the harness binary gets into
  a task container; the blessed typed method is a released artifact
  pinned by URL and content checksum — the same discipline as pinned
  npm targets and the task-directory digest. Unpinned install steps
  are rejected before launch, and install-only preflight (ADR 0012)
  proves declared-harness installation in a real task container at
  zero token cost, exactly as it does for built-ins.
- **One evidence contract, two transports.** In yacht-run mode the
  launcher reads `yacht.harness-evidence.v1` from stdout or the
  evidence file; in Harbor mode the generic agent collects the same
  document inside the task container and maps it into the trial
  result, so trials carry usage and tool evidence with the same
  fidelity as the built-in agents. A harness that targets the contract
  once is measurable on every course kind.

## Consequences

- A harness YACHT has never heard of can be measured by writing config
  and emitting one JSON document — no fork, no in-tree adapter. yach
  integrates this way first and keeps a friction log; an in-tree
  adapter, if it ever exists, becomes an optimization rather than a
  gate.
- The evidence schema becomes a public contract with the same standing
  as the course schemas: versioned, validated, documented. Harness
  authors get a stable target; YACHT gets evidence quality that does
  not depend on guessing stream formats.
- Requiring evidence on the custom path trades convenience for honesty:
  a harness without usage reporting shows failed attempts, not
  estimated numbers. That is deliberate — the same posture as failing
  loudly on an exit-0 run without a result (ADR 0008).
- The reported-vs-estimated flag surfaces a latent problem in built-in
  metrics; reports and aggregates can now annotate or exclude estimated
  usage instead of unknowingly comparing it against reported usage.
- Sequencing means a window in which a declared harness runs SWE-bench
  and LiveCodeBench but not Harbor-format courses; the window is a
  delivery order inside one committed design, not an open question, and
  closing it changes no declarations — the Harbor slice adds the
  generic agent and enforces the install pins, nothing else.
- The install declaration becomes part of the trust surface: a
  checksummed artifact pin says exactly which harness build ran, and
  provenance records it the way harness_version is recorded today.
  Harnesses without pinned release artifacts must produce one to be
  measurable on Harbor courses — a deliberate bar, matching the
  pinned-npm rule for rigging.
- Config-declared subprocess execution is not a new trust boundary —
  runtime commands are already config-authored — but the declaration
  doc says plainly that a harness declaration is code execution and
  carries the same standing as the rest of the config.
