# LiveCodeBench Course

The `livecodebench` course runs LiveCodeBench code-generation problems
through the benchmark's official evaluator (ADR 0014). It is a yacht-run
course: agents attempt each problem in YACHT's own pinned runtime through
a harness adapter, respond with solution code, and the official
`lcb_runner` custom evaluator grades the code afterwards — the same
shape as SWE-bench, and the maintained non-Harbor course committed in
ADR 0012.

## Configuration

```toml
[course.adapter]
kind = "livecodebench"
dataset = "livecodebench/code_generation_lite"
split = "release_v1"            # pinned dataset release (release_v1..v6)
harness = "docker"
instance_ids = ["2727", "abc301_a"]
start_date = "2023-05-01"       # contest-date window, required
end_date = "2023-05-14"
```

- `split` pins the dataset release; there is no floating "latest".
- The **contest-date window** is required. It is the benchmark's own
  contamination-control axis: restricting problems to contests after a
  model's training cutoff is how LiveCodeBench claims freshness, and the
  window is recorded in every artifact as provenance. `instance_ids`
  select tasks inside the window.
- Agents must respond with a JSON object carrying a non-empty `code`
  string (Python only): completed starter code for function-style
  problems, or a stdin/stdout program for contest-style problems. The
  problem statement and starter code are placed in the prompt.

## Pipeline shape

Problems are loaded through the pinned `lcb-runner` container image
(built from `containers/lcb-runner`, the official repository at a pinned
commit): the dataset's Hugging Face loading script cannot run under
modern `datasets` releases, so the same environment that grades the code
also supplies the task context, cached under `~/.cache/yacht/lcb-hf`.

Grading satisfies the official evaluator's whole-window contract by
padding: every problem in the window gets an output entry, attempted
problems carry the agent's code, and unattempted problems carry empty
code that is excluded from YACHT's submitted set and reported only as a
padding count. The evaluator executes the generated code against public
and private test cases **inside the lcb-runner container** — never on
the host — and per-question results translate into the normalized
grading report that scorecards, statistics (ADR 0013), and the dashboard
consume.

## Example

`examples/container-claude-code-livecodebench-smoke.toml` compares two
Claude models on two problems from a pinned May 2023 window:

```sh
docker build -t yacht/claude-code-runtime:claude-2.1.211 containers/claude-code-runtime
docker build -t yacht/lcb-runner:lcb-28fef95 containers/lcb-runner

uv run yacht run examples/container-claude-code-livecodebench-smoke.toml \
  --logbook /private/tmp/yacht-livecodebench-smoke \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY
```

Requirements: Docker running, uv, and `ANTHROPIC_API_KEY` exported. The
first run downloads the pinned dataset release into the host cache.

## Caveats

- Python-only, single-sample pass@1: verdicts speak to one generation
  per problem, and the ADR 0013 evidence grades apply as everywhere.
- Results come from the official evaluator at a pinned commit, but a
  historical window (like the example's May 2023) predates current model
  cutoffs — use a post-cutoff window when contamination control is the
  point of the comparison.
