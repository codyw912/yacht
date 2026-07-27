# Custom Harnesses: Config-Declared Adapters and the Evidence Contract

YACHT can measure harnesses it does not ship (ADR 0016). A
`[harnesses.<name>]` table in the regatta config declares a harness;
runtimes reference it by name exactly as they reference the built-ins
(`pi`, `claude-code`). No in-tree adapter, no fork — the integration
surface is one config table and one JSON document.

```toml
[harnesses.yach]
prompt = "argument"    # how the prompt is passed: "argument" | "stdin"
evidence = "stdout"    # where evidence comes from: "stdout" | "file"

[runtimes.yach-container]
backend = "container"
image = "registry.example.com/yach-runtime:0.3.0"  # your image, your registry
command = ["yach", "run", "--model", "claude-haiku-4-5"]
harness = "yach"
required_secrets = ["anthropic"]
```

Declared names must not shadow built-ins. A harness declaration is
config-authored code execution, with the same standing as the rest of
the config (runtime commands always were).

Which config field carries the invocation depends on the course kind,
and mixing them up is the most common integration mistake:

- **yacht-run courses** (SWE-bench, LiveCodeBench): the runtime's
  `command` is the invocation — `argv = command_prefix +
  runtime.command`, plus the prompt per the declaration's `prompt`
  mode. The declaration's `command` field is ignored here, and there
  is no `{model}` substitution: write the model flag literally, one
  runtime per model configuration (the same convention the built-in
  examples use).
- **Harbor-format courses**: the declaration's `command` (with
  `{model}` substitution) is the in-container invocation — the runtime
  recipe is the harbor launcher and carries no harness argv. See
  "Harbor-format courses" below.

## The launch contract

What YACHT does when it runs your harness — uniform across built-in and
declared adapters:

- **One autonomous session.** `argv = command_prefix + runtime.command`,
  plus the prompt as the final argument (`prompt = "argument"`) or on
  stdin (`prompt = "stdin"`). The harness is expected to run one
  full-auto session to completion in the task working directory — no
  interactive approvals. Task workdirs are disposable.
- **Exit codes.** Nonzero is a failed attempt: recorded as evidence,
  counted against the vessel, never retried silently. Zero means the
  attempt completed — the evidence and the grader decide whether it
  *succeeded*.
- **Transcript.** YACHT's launcher writes the transcript artifact
  (argv, stdout, stderr, response, evidence, timings). The harness has
  no transcript obligation.
- **Environment.** The subprocess env is filtered: the harness sees the
  runtime recipe's declared env, injected secrets resolved from the
  config's secret references, and the sanitized base the backend
  provides — not the parent process's environment.

## The evidence contract

Instead of YACHT parsing your output stream, your harness emits one
JSON document — `yacht.harness-evidence.v1` — either as the final
non-empty line of stdout (`evidence = "stdout"`) or written to the path
YACHT provides in `$YACHT_EVIDENCE_PATH` (`evidence = "file"`).
`evidence = "file"` currently works on host backends only — the
evidence path cannot cross the container boundary yet, and config
validation rejects the combination — so container runtimes use
`stdout`:

```json
{
  "schema": "yacht.harness-evidence.v1",
  "response": "final assistant message text",
  "usage": {
    "input_tokens": 12840,
    "output_tokens": 1622,
    "cache_read_tokens": 9100,
    "cache_write_tokens": 0
  },
  "tool_calls": [
    {"name": "read_file", "count": 7},
    {"name": "bash", "count": 3}
  ],
  "cost": {"total_usd": 0.0182},
  "model": "claude-haiku-4-5",
  "extras": {"session_id": "..."}
}
```

- `schema`, `response`, and `usage.input_tokens`/`usage.output_tokens`
  are required; `tool_calls` (with per-tool counts), `cost`, `model`,
  and `extras` are optional but feed reports and provenance when
  present.
- **The custom path never estimates.** A run that exits 0 without valid
  evidence fails loudly — a declared harness that does not emit the
  contract is a broken integration, not a degraded measurement. (For
  the same reason, all attempt metrics now carry `usage_source`:
  `reported` or `estimated`. Declared harnesses are always `reported`;
  built-in adapters mark their fallback estimates honestly.)

## Mapping harness-native output (ADR 0017)

Most harnesses should not emit yacht's schema at all: declare a
mapping from the harness's existing machine-readable output instead,
and the wire format above becomes YACHT's internal normal form.

```toml
[harnesses.yach.evidence_map]
response = "response.text"
input_tokens = "usage.input_tokens"
output_tokens = "usage.output_tokens"
tool_calls = "tools.calls"          # [{name, count}] or [names]
model = "model"                     # optional
cost_usd = "usage.cost.total"       # optional
usage_reported = "usage.reported"   # optional boolean
```

Paths are dotted key lookups into the parsed JSON (same transports:
final stdout line or the evidence file). `response`, `input_tokens`,
and `output_tokens` are required; a missing or wrong-typed mapped path
fails the attempt loudly — no estimates. `usage_reported = false`
surfaces as `usage_source: "unreported"` in metrics, so honest zeros
from a provider that reported nothing never masquerade as
measurements. Emitting `yacht.harness-evidence.v1` directly remains
valid (it is the identity mapping).

## Provisioning the harness binary

The runtime delivers the binary; no new mechanism exists or is needed:

- **Container backend** (recommended): bake the harness into a runtime
  image, pinned by tag. Private registries and locally built images
  work — YACHT only ever runs the image name you give it. The image
  must be **entrypoint-neutral**: YACHT appends `runtime.command`
  directly after the image name, so an `ENTRYPOINT ["yach"]` image
  would execute `yach yach run ...`.
- **host-nix backend**: the flake provides the harness on PATH.

Secret values are supplied at run time, never read implicitly:
`[secrets.x] source = "env" name = "VAR"` declares that the value is
injected into the runtime under `VAR` — the value itself comes from
the CLI, e.g. `--secret x=@env:VAR` (read `VAR` from your shell) or
`--secret x=<literal>`. A declared secret without a `--secret` value
fails before launch with the flag named in the error.

Agent-prompt preflight (`kind = "agent-prompt"`) runs a real prompt
through the declared harness before tokens are spent on tasks — the
cheap way to prove the binary, the evidence emission, and the secrets
all work.

## Harbor-format courses

The same declaration runs native-rollout Harbor courses
(Terminal-Bench, Aider Polyglot, custom evals) once it adds the two
fields those courses need — the run command and a pinned install:

```toml
[harnesses.yach]
prompt = "argument"
evidence = "file"
command = ["yach", "run", "--model", "{model}"]

[harnesses.yach.install]
path = "dist/yach-linux-arm64"   # or url = "https://..."
sha256 = "<sha256 of the artifact>"

[runtimes.harbor-yach]
backend = "harbor"
image = "yacht/harbor-launcher:harbor-0.20.0"
harness = "yach"
harness_version = "0.1.0"
```

- YACHT's generic Harbor agent resolves the artifact on the launcher
  side (local `path`, resolved against the config file, or a `url` it
  downloads), verifies the sha256, uploads the binary into the task
  container, and verifies the checksum again in-container before
  anything runs. Unpinned installs are rejected; the pin is provenance
  for exactly which harness build ran.
- `command` is the in-container invocation: the first element maps to
  the installed binary when it matches the harness name, and `{model}`
  is substituted with the vessel's model. The prompt follows the
  declaration's `prompt` mode; evidence follows its `evidence` mode
  (for `file`, YACHT sets `$YACHT_EVIDENCE_PATH` inside the container).
- Evidence maps into the Harbor trial result (tokens, cache, cost), so
  declared-harness trials carry the same usage surface as the built-in
  agents. A run without valid evidence is a trial error — never an
  estimate.
- The artifact should be a static single-file linux build (x86_64 /
  aarch64 as your task images require): task environments are
  user-authored images, and glibc is not guaranteed.
- Install-only preflight covers declared harnesses like built-ins:
  installation is proven in a real task container before tokens are
  spent.
