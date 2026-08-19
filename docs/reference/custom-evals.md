# Custom Evals: User-Authored Harbor-Format Task Directories

The `custom-eval` course runs evals you write yourself (ADR 0015). A
course points at a local directory of Harbor-format tasks and runs them
through the same pinned-launcher foundation as the registry Harbor
courses (ADR 0012): Harbor builds each task's environment container,
installs the pinned agent inside it, runs the agent, runs your verifier,
and records a per-trial result. Everything downstream — normalized
grading reports, statistical verdicts, provenance, the dashboard — works
unchanged.

YACHT does not generate or revise evals. Tools that do (agent skills
that mine repositories and traces, propose abilities, and emit tasks)
produce exactly the format this course consumes; YACHT is the runner
that turns those tasks into evidence-backed comparisons.

## Running generated evals

Eval-generation tooling that emits Harbor tasks plugs in directly. For
example, LangChain's eval-engineering skill
([langchain-ai/langchain-skills](https://github.com/langchain-ai/langchain-skills),
installable with `npx skills add langchain-ai/langchain-skills --skill
eval-engineering`) inspects an agent repository and optional traces,
interviews you about what to test, and scaffolds standard Harbor task
directories under `evals/` via `harbor task init`. Point a custom-eval
course at that directory and the generated evals run under YACHT's
pins, digest, statistics, and provenance as-is:

```toml
[course.adapter]
kind = "custom-eval"
dataset = "evals"   # the directory the generation tooling wrote
split = "v1"
harness = "harbor"
```

The division of labor is deliberate: generation tooling decides what to
test and drafts the tasks; YACHT provides the hermetic reruns, the
content-digest pin, the evidence-graded comparisons, and the preserved
verifier trajectories that make the results worth trusting over time.

## Task directory layout

Each task is a directory in the Harbor task format:

```
my-evals/
└── hello-task/
    ├── task.toml            # timeouts and metadata (all fields optional)
    ├── instruction.md       # the message the agent receives
    ├── environment/
    │   └── Dockerfile       # the task container the agent acts inside
    ├── solution/
    │   └── solve.sh         # oracle solution (optional but recommended)
    └── tests/
        └── test.sh          # verifier: runs after the agent finishes
```

- The **verifier** (`tests/test.sh`) runs inside the task container
  after the agent and reports its score by writing
  `/logs/verifier/reward.txt` (a single float; `1` is resolved) or
  `/logs/verifier/reward.json`. YACHT treats reward >= 1.0 as resolved.
- The **environment** must contain whatever the agent needs to work —
  including the agent's own runtime: yacht's `claude-code` Harbor agent
  installs via npm, so the image needs Node (the example uses
  `node:22-bookworm-slim`). The `install-only` preflight check is the
  cheap way to find out whether installation works.
- The **oracle solution** (`solution/solve.sh`) lets you validate the
  task at zero token cost: run Harbor's `oracle` agent against the
  directory and confirm the verifier awards `1.0` — if the reference
  solution doesn't pass your own verifier, an agent's failure means
  nothing.
- A working example lives at `examples/custom-evals/hello-task`.

## Episodic tasks

A task can declare a *relay*: several cold agent sessions run in sequence
against one persistent environment, with files on disk as the only
memory between them (ADR 0025). This is how you test claims about
institutional memory — session-handoff frameworks, memory files, context
docs — where the thing under test is whether a fresh session does less
rediscovery because of what a prior session left behind. A working
example lives at `examples/custom-evals/relay-task`.

### The `[episodes]` table

Add an `[episodes]` table to `task.toml` to activate the feature:

```toml
[agent]
# Covers the whole relay: every episode plus inter-episode verification.
timeout_sec = 900.0

[episodes]
max = 2
verify_between = true
max_turns = 15
timeout_seconds = 300
```

- `max` (required, integer >= 1) — the number of episodes. `max = 1` is
  the same as omitting the table entirely; a value greater than 1
  activates the relay.
- `verify_between` (default `false`) — run the verifier between
  episodes; see below.
- `continue_instruction` (default `"Continue work on the project."`) —
  the instruction an episode receives when no delta file supplies one.
- `max_turns` (optional) — a per-episode turn cap, enforced
  harness-natively. Only harnesses that can actually apply it accept it
  (see Budgets below); on any other harness it is a render-time error,
  never a silent no-op.
- `timeout_seconds` (optional) — a per-episode wall-clock backstop.

Unknown keys, a non-boolean `verify_between`, or a blank
`continue_instruction` are `ConfigError`s at render time, before any
container starts. Note that `task.toml` is required for every
custom-eval task, episodic or not.

Episode 1 always receives the task's normal `instruction.md`. `[agent]
timeout_sec` is the *trial's* budget, not one episode's — because a
relay is one Harbor trial, it must cover every episode plus any
inter-episode verification, not just the first.

### Delta files

Later episodes can each receive their own instruction via
`episodes/00k.md` files (three digits, contiguous starting at `002`):

```
relay-task/
├── task.toml
├── instruction.md      # episode 1
└── episodes/
    └── 002.md           # episode 2
```

Episode *k* >= 2 receives `episodes/00k.md` **alone** if it exists —
never unioned with the original instruction or any earlier delta — or
`continue_instruction` if it doesn't. This is what makes drip-fed
requirement schedules expressible: each episode sees only what a real
returning session would see, plus whatever the prior episode chose to
leave on disk. `examples/custom-evals/relay-task/episodes/002.md`
delivers a new requirement and points the agent at
`/app/NOTES.md`, which episode 1's `instruction.md` asked the agent to
leave for a future session.

A gap in the numbering, a file past `max`, an unknown filename shape, or
an empty delta file are all `ConfigError`s at render time. Delta files
with no `[episodes]` table is also an error — the table is what
activates the feature.

### Budgets: harness-native caps, wall-clock backstop

Per-episode caps come from the harness itself, so a capped episode ends
the way a real session ends, transcripts intact — not the wall clock.
For `claude-code`, `max_turns` is passed as `--max-turns`; hitting it is
a normal episode ending (`ended: "cap"`, from the stream result's
`error_max_turns` subtype), not a failure. Declared harnesses opt into
the cap by naming a `{max_turns}` placeholder somewhere in their declared
`command`, which the harbor-side runner substitutes. Both mismatches are
hard errors rather than silent no-ops: a declaration that names
`{max_turns}` while the task sets no cap raises at run time, and a task
that sets a cap while the declaration has no placeholder is refused at
render time — being declared is not an exemption, since dropping the cap
is exactly as silent there as on a harness with no flag at all.
Declared episodes have no cap signal of their own — `ended` for them is
`natural`, `timeout`, or `error` only, never `cap`.

OMP and Codex have no turn-cap flag, so they cannot honor `max_turns` at
all. Rather than accept the key and drop it — which would make two
vessels look like they ran under the same budget when only one did — the
job render refuses:

```
episodic max_turns is not enforceable on the omp harness and would be
silently ignored: relay-task; remove max_turns from the task, cap the
episode with timeout_seconds instead, or run the comparison on a harness
that enforces a turn cap (claude-code)
```

Episodes themselves still work on OMP and Codex; only the cap is
refused. If those CLIs gain a real turn cap, add the harness to
`MAX_TURNS_ENFORCING_HARNESSES` in `yacht/courses/episodes.py` and pass
the flag — the rejection is a statement about today's harnesses, not a
permanent limit.

`timeout_seconds` is the driver's own backstop for hangs; hitting it
ends the episode with `ended: "timeout"`, itself a normal ending, and
the relay moves on to the next episode. Only a harness crash
(`ended: "error"`) aborts the trial — and it does so preserving whatever
episodes already completed.

pi does not support episodic trials yet: an `[episodes]` table on a task
run under the `pi` harness fails at render time, before any container
starts, never as a silent single-shot fallback.

### The `verify_between` contract

With `verify_between = true`, yacht mirrors Harbor's verifier protocol
against the live environment after each non-final episode: it uploads
the task's `tests/`, execs `/tests/test.sh`, reads
`/logs/verifier/reward.{json,txt}`, relocates those files into the
episode's evidence directory, and removes `/tests` and the reward files
from the container. `verify_between` requires `tests/test.sh` to exist —
its absence is a `ConfigError` at render time.

Setting the flag is the task author's assertion that the verifier is
**side-effect-free**; the upload/exec/removal sequence is hygiene, not a
guarantee, and the documented contract puts the leakage risk on the
author. The inter-episode exec always runs `tests/test.sh` directly and
ignores the task's `[verifier]` `env` settings (a v1 limitation) — it
does not reproduce arbitrary verifier configuration, only the script
itself.

A reward >= 1.0 between episodes ends the relay early and records
`to_resolution`. It never grades the trial: the final Harbor-run
verifier, run once after the last episode, remains grading truth. If a
mid-relay pass is contradicted by the final verdict, both are preserved
as a visible mismatch in the evidence — yacht never resolves the
disagreement in its own favor.

### Evidence

Per-episode artifacts land under the trial's agent log directory:

```
<trial>/agent/episodes/
├── 001/
│   ├── instruction.md
│   ├── claude-code.txt          # or run-stdout.txt/run-stderr.txt +
│   │                             # harness-evidence.json (declared harnesses)
│   └── sessions-manifest.json   # claude-code only
├── 002/
│   ├── instruction.md
│   ├── ...
│   └── reward.json               # + reward.txt, episode-stdout.txt,
│                                  # when verify_between ran here
└── summary.json                  # {count, items, to_resolution?}
```

`sessions-manifest.json` is written only for `claude-code` (its run
loop snapshots the harness's session directory after every episode);
declared harnesses have no analog. Where it exists, it is cumulative —
each episode's copy lists every session file written so far, not just
that episode's own. Attributing a session to a specific episode means
diffing episode *k*'s manifest against episode *k-1*'s.

The task attempt carries a validated top-level `episodes` block —
`{count, items, to_resolution?}`, where each item has `index`, `ended`
(`natural` | `cap` | `timeout` | `error`), and optional `started_at`,
`finished_at`, `usage`, `cost_usd`, `reward`. Attempt-level usage and
cost sum across episodes — except when any episode records no cost
(e.g. it timed out before the harness emitted its result line), in
which case the trial-level cost falls back to the harness's own
accounting, which for claude-code reflects only the final episode's
stream; relay cost is then undercounted, and the per-episode records
above show the gap.

### Statistics

One trial contributes exactly one paired outcome, however many episodes
it ran. Episode metrics — endings, rewards, `to_resolution`, per-episode
usage — are descriptive evidence for reading what happened inside the
relay; they never enter the sign test and never count toward repetition
budgets (ADR 0021, ADR 0023). A repetition of an episodic task is a
complete fresh relay: new container, new workspace, every episode run
again from episode 1 (ADR 0025).

## Configuration

```toml
[course.adapter]
kind = "custom-eval"
dataset = "custom-evals"     # path to the task directory,
                             # relative to this config file
split = "v1"                 # your revision label for this eval set
harness = "harbor"

[[course.tasks]]
id = "hello-task"            # must match a task directory name
title = "Write a greeting file in the task container"

[runtimes.harbor-claude]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "claude-code"
harness_version = "2.1.215"
required_secrets = ["anthropic"]
```

- `dataset` is the task directory path, resolved against the config
  file's directory. `split` is a label you choose for this revision of
  the eval set; it groups runs in reports and the dashboard.
- Everything else — the `harbor` runtime backend, pinned
  `harness_version`, rigging, `install-only` preflight, provider
  credentials via environment — works exactly as on the registry Harbor
  courses; see the Terminal-Bench reference.

## The content digest is the pin

Registry courses pin datasets by content-addressed reference; a local
directory has no registry, so YACHT pins by content instead:

- The course handoff computes a sha256 digest over every file's
  relative path and bytes in the task directory and records it as
  `content_digest` in the adapter block of every pipeline artifact.
- At launch, the harness recomputes the digest before running Harbor
  and refuses to launch if it differs — a task edited between planning
  and launch fails loudly instead of silently measuring different
  content.
- Two runs are comparable when their digests match. A changed eval is
  visibly a different eval, whatever its `split` label says.

The tasks themselves are your responsibility: task environments execute
arbitrary Dockerfiles under the launcher's container boundary, the same
standing as any Harbor dataset, with a user-authored source.

## Judging the verifier, not just the agent

First-draft verifiers are rarely right: agents reward-hack tasks by
satisfying a proxy without doing the work. Harbor records both sides of
every trial under the vessel's `harbor-trials/` directory — the agent's
trajectory and the verifier's output — and YACHT preserves that
directory in the logbook. When a result looks too good, read the trial:
what did the verifier actually credit? Revise the task, environment, or
verifier, bump `split`, and rerun; the digest records that the eval
changed.

## Validating a task at zero token cost

```sh
# 1. Oracle run: does the reference solution pass the verifier?
#    (writes a harbor run config pointing at your task directory, then)
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$WORK:$WORK" -v "$TASKS:$TASKS" \
  yacht/harbor-launcher:harbor-0.20.0 \
  harbor run -c "$WORK/harbor-run-config.json" --yes --quiet

# 2. Install-only preflight: does the pinned agent install in your
#    environment image? Declared in the runtime's preflight checks:
#    { name = "agent-install", kind = "install-only" }
```

The example regatta (`examples/custom-eval-claude-code-versions-smoke.toml`)
composes all of this: two pinned Claude Code versions on the example
task, install-only preflight, and the digest pin.

## Measuring a skill claim

The most common custom-eval question is a treatment comparison: does a
skill (or MCP server, or any rigging) actually change what the agent
produces? `examples/custom-eval-skill-ab-smoke.toml` is that experiment
in full: the same pinned Claude Code runs
`examples/custom-evals/convention-task` with and without a
team-conventions skill installed by rigging. The task requires
conventions that are documented only in the skill, so the skill's
effect surfaces as resolution — measured by the verifier, not judged
from transcripts.

The same shape measures MCP server delivery (ADR 0022):
`examples/custom-eval-mcp-ab-smoke.toml` runs
`examples/custom-evals/mcp-task` with and without a pinned filesystem
MCP server. The `mcp-server` install step's target alone makes delivery
measurable — task attempts record a namespace expectation
(`mcp__<server>__`), the scorecard reports whether any of the server's
tools fired, and `observed_tools` lists which. In a live 3-repetition
run of this example the instrument distinguished a repetition where the
server was connected but unused (delivery: not-delivered) from two
where the agent called `mcp__files__list_directory` — exactly the
distinction that separates "the treatment did nothing" from "the
treatment never fired".

A harness without native MCP support can still carry a server, if a
rigged tool declares that it provides `mcp-server` for that harness
(ADR 0024). `examples/custom-eval-pi-mcp-ab-smoke.toml` runs the same
comparison on pi: `pi-mcp-adapter` declares
`provides = [{ method = "mcp-server", harness = "pi" }]`, the
capability gate accepts the `files` server's install step on that
strength, and yacht renders the adapter's `.pi/agent/mcp.json` with
`directTools` on and the `mcp` tool prefix, which names the server's
tools `mcp__files_<tool>`. Delivery evidence keys on that convention
wherever the names appear — as directly registered tools or as the
inner tool name a call through the adapter's `mcp` gateway carries.
Without a declared provider the gate still refuses the step, and
without the namespace guarantee the server reports unmeasured rather
than guessed at.

### What a delivery stage claims

A skill reports three stages — `available`, `selected`, `loaded` — each
`observed`, `absent`, or `unmeasured`. The states are not
interchangeable: `absent` means the evidence was there and showed the
stage did not happen, `unmeasured` means the stream could not tell us.
Reports print a stage with no measured attempts as `unmeasured` rather
than `0/0`, because `0/0` reads like a measured zero.

Two rules keep those states honest:

- **A failed tool call is not delivery.** An agent that reads
  `skill://motif-work` and gets `Unknown skill: motif-work` back has
  loaded nothing. OMP flags that read with `isError`, and the error text
  arrives as ordinary text content, so a parser that only checks for
  non-empty text would score the failure as `loaded: observed`. Yacht
  records `loaded: absent` instead. It still leaves `available`
  `unmeasured`: an errored read proves the body did not arrive, not why,
  and a nonzero shell exit on a command that merely mentions a skill path
  says even less.
- **Installation is not observation.** An install-only preflight check
  proves the treatment reached the environment. It says nothing about
  whether the agent then found and read it, and it never fills in these
  stages. The two live in separate artifacts on purpose; a report that
  merged them would let setup masquerade as behavior.

Two properties make the result trustworthy where a raw pass-rate delta
is not:

- **The verdict is graded by evidence** (ADR 0013). One run of one task
  is an observation, and the report says so; run the comparison with
  `--repetitions` to accumulate discordant outcomes until the sign
  test can actually distinguish the treatment from noise.
- **Everything that could vary is pinned**: the harness version, the
  task content (digest), the skill content (declared in config,
  applied per-trial in a fresh container). When the delta moves, it is
  the treatment moving.
