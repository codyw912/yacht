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
