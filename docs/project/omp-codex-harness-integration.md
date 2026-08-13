# OMP and Codex harness integration handoff

Status: proposed

Implementation order: [OMP and Codex harness expansion](omp-codex-harness-expansion.md).

## Outcome

Make OMP and Codex first-class Yacht harnesses so the same course can compare
their behavior, including skill delivery and multi-episode continuity, without
requiring either harness to emit Yacht-native evidence.

This should remain generic harness work. Motif is the first demanding consumer,
not a special case in Yacht core.

## Why declared harnesses are not the whole answer

Both CLIs already have usable non-interactive surfaces:

- OMP: `omp -p --mode json --no-session ...`
- Codex: `codex exec --json --ephemeral ...`

A declared harness is suitable for an initial smoke, but its evidence mapping
expects one JSON object and dotted field extraction. OMP and Codex emit JSONL
event streams whose final response, aggregate usage, tool calls, skill loading,
and failure state require event-aware parsing. Thin first-class adapters let
Yacht consume the native streams without wrappers becoming an untracked part of
the treatment.

## Required neutral evidence

Each adapter should preserve the native transcript and normalize:

- final response and process exit;
- input, output, cache-read, and cache-write tokens when reported;
- cost when reported, otherwise explicitly unreported;
- model, provider, harness version, and invocation arguments;
- tool calls with native names and counts;
- session or turn termination reason;
- skill availability, selection, and content loading when observable.

Do not reduce skill delivery to a generic `read` call. Record native evidence
and map it to a neutral progression:

1. `available`: the skill was present in harness discovery;
2. `selected`: the harness or model chose the named skill;
3. `loaded`: the skill instructions were actually inserted or read.

OMP exposes a `skill-prompt` session event for explicit invocation. Codex may
expose skill initialization or reads differently. Missing native evidence must
remain `unmeasured`, not inferred from a successful outcome.

## Runtime and rigging contract

For each harness:

- pin the CLI version in the runtime recipe and capture the resolved version;
- install into an isolated Harbor task environment without copying user-home
  configuration or credentials;
- inject only declared provider secrets;
- use the harness's native project-scoped skill/plugin surface;
- preflight the binary, model/provider access, skill discovery, and writable
  workspace before task tokens are spent;
- run non-interactively with approvals disabled only because the enclosing task
  container is disposable and externally isolated.

Skill rigging should express a logical `agent-skill` once while allowing the
adapter to render the appropriate native layout. Avoid making `.claude/skills`
the generic skill-install contract.

## Comparison design

Harness comparisons should use a factorial shape:

| Harness | Control | Treatment |
| --- | --- | --- |
| Codex | stock harness | harness + skill |
| OMP | stock harness | harness + skill |

The primary estimates are the treatment effect within each harness. Compare
those effects across harnesses; do not treat the raw OMP-versus-Codex outcome
delta as the effect of the skill. Hold course digest, prompt, model/provider,
permissions, runtime resources, and episode budgets constant where the
harnesses permit it.

If no model can be held constant across every harness, use a connected design:
OMP and Codex on one OpenAI model, and OMP and Claude Code on one Anthropic
model. Record the limitation in provenance.

## Episodic support

Motif continuity and approval-boundary evals need fresh harness processes over
one persistent workspace. Both adapters should support Yacht's existing episode
plan:

- episode 1 receives the task instruction;
- later episodes receive only their declared continuation instruction;
- each episode starts a cold CLI process with no native session resume;
- files are the only continuity channel;
- per-episode native transcripts and usage are preserved;
- one relay remains one statistical observation.

Codex and OMP have native time limits or resumability features, but the relay
must not use session resume. Use Yacht's wall-clock backstop and a documented
harness-native turn cap where one exists.

## Suggested implementation slices

The expansion plan reorders these so skill-install generalization lands
first (as slice 0). Follow
[that order](omp-codex-harness-expansion.md#agreed-order), not the
list below.

1. Add native JSONL parser fixtures and pure parser tests for each harness.
2. Add single-shot prompt and task adapters with version/provenance capture.
3. Generalize agent-skill rigging and delivery evidence beyond Claude Code.
4. Add install-only and agent-prompt preflight coverage.
5. Add Harbor agents and one token-free or minimal-token smoke per harness.
6. Add episodic execution and per-episode evidence.
7. Run a pinned cross-harness course and verify report comparability.

## Acceptance criteria

- A malformed or incomplete native stream fails or degrades explicitly; it is
  never silently counted as measured evidence.
- Stock and skill-rigged vessels can run the same custom-eval task.
- Reports distinguish skill availability, selection, loading, and outcome.
- Tool and usage totals can be traced back to preserved native events.
- OMP and Codex can execute a two-episode cold-session relay in one workspace.
- Existing Pi and Claude Code behavior and artifact schemas remain compatible.

## Initial consumer

The first consumer can be the separate Motif eval suite. Begin with one-shot Pi
cases while these adapters are built, then use the same task content for Codex
and OMP and add the approval/continuity relays once episodic support exists.
