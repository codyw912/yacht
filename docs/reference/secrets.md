# Secrets

Yacht runs real coding harnesses against real providers, so a live run
needs a real API key. This page describes the two halves of that: how
Yacht itself handles a secret once it has one, and how contributors get
one to Yacht without leaving it lying around.

## Yacht's own secret model

A regatta config declares *which* secret a runtime needs, never the
value:

```toml
[secrets.anthropic]
source = "env"
name = "ANTHROPIC_API_KEY"

[runtimes.container-claude-code]
backend = "container"
required_secrets = ["anthropic"]
```

At run time you supply the value:

```sh
uv run yacht run <config> --secret anthropic=@env:ANTHROPIC_API_KEY
```

`@env:VARIABLE` means "read it from this environment variable". Yacht:

1. resolves each `@env:` reference exactly once, at argument-parse time;
2. removes the referenced variable from its own environment as soon as
   every reference resolves (all-or-nothing: a parse or lookup failure
   raises before anything is removed);
3. keeps the value only in its in-memory secret map;
4. reintroduces it into the environment of a runtime whose
   `required_secrets` name that logical secret — and nowhere else.

The consequence worth knowing: a helper subprocess Yacht spawns for
something unrelated — a `git` call, a dataset download, a rigging install
for a vessel that declared no secrets — cannot inherit the key, because
it is no longer in the ambient environment. Only the exact variable names
you referenced are removed; nothing is matched by prefix or pattern.

Container and Harbor runtimes still work the way they always have:
`docker run --env ANTHROPIC_API_KEY` passes the variable **by name**, and
Yacht supplies the value in the environment it hands to `docker`. The
value never appears in a command argument, a plan, or an artifact —
artifacts record redacted references:

```json
"secret_refs": [
  { "name": "anthropic", "source": "env", "ref": "ANTHROPIC_API_KEY", "redacted": true }
]
```

Two logical secrets may reference the same variable; each gets the value
and the variable is removed once.

## Why SecretSpec

Yacht's model answers "which runtime may see this key". It says nothing
about where the key comes from, and the usual answer — a long-lived
`export ANTHROPIC_API_KEY=...` in a shell profile — hands that key to
every process you ever start, including whichever coding agent happens to
be running in that terminal.

[SecretSpec](https://secretspec.dev) closes that gap without changing
Yacht: it resolves declared secrets from *your* provider and injects them
into *one* child process. Yacht's `--secret name=@env:VAR` then picks the
variable out of that child environment, and scrubs it. The two models
compose: SecretSpec decides how long a secret exists, Yacht decides which
runtime sees it.

Yacht itself never requires SecretSpec. It has no dependency on it and no
knowledge of it: `--secret NAME=@env:VARIABLE` accepts a variable from
any supplier — a plain `export`, a CI secret, `dotenv`, `op run`, a
Kubernetes secret, `docker -e`. The contributor environment provides a
pinned SecretSpec release (`nix/secretspec.nix`, currently 0.19.1)
because this is the workflow the project documents and pinning beats a
`curl | sh` installer — not because anything in Yacht depends on it.

Yacht commits a provider-neutral [`secretspec.toml`](../../secretspec.toml):

```toml
[project]
name = "yacht"
revision = "1.0"

[profiles.default]
ANTHROPIC_API_KEY = { description = "Anthropic API key for evaluated harnesses" }
OPENAI_API_KEY = { description = "OpenAI API key for evaluated harnesses" }

[scopes.anthropic]
secrets = ["ANTHROPIC_API_KEY"]

[scopes.openai]
secrets = ["OPENAI_API_KEY"]
```

That is the whole manifest: which secrets exist, and which subsets a
single command may resolve. No provider, no vault, no item, no field, no
values. Yacht is provider-neutral and stays that way.

## Selecting your provider (once, privately)

Each operator points SecretSpec at their own store in user-global
configuration, which is never committed:

```sh
secretspec config global init \
  --provider <provider-uri> \
  --profile default
```

`<provider-uri>` is yours to choose and yours to keep out of this
repository: `keyring`, `pass`, `sops://...`, `dotenv:~/.config/...`, a
1Password vault, a cloud secret manager. Nothing about that choice
belongs in `secretspec.toml`, and no vault, item, or field name should be
committed anywhere here.

Store the two secrets under the names the manifest declares:

```sh
secretspec set ANTHROPIC_API_KEY
secretspec check
```

`secretspec check` reports which declared secrets resolve without
printing values.

### When your items do not match the convention

Global configuration selects a provider, but it cannot say which item and
field inside that store hold a given key. Those per-secret coordinates
are yours — they must not be committed. Put them in an uncommitted
`secretspec.local.toml` that extends the neutral manifest:

```toml
[project]
name = "yacht"
revision = "1.0"
extends = ["secretspec.toml"]

[providers]
store = "<provider-uri>"

[profiles.default]
ANTHROPIC_API_KEY = { ref = { item = "<item>", field = "<field>" }, providers = ["store"] }
```

`extends` inherits the declarations *and* the scopes, so this file only
says where values live:

```
$ secretspec run -f secretspec.local.toml --reason … --scope nope -- true
Invalid scope: 'nope' is not defined … Available scopes: anthropic, openai
```

`/secretspec.local.toml` is gitignored, and `yacht-run-anthropic` /
`yacht-run-openai` pass `--file` for it automatically when it exists.

Keep the coordinates out of the committed manifest for a second, concrete
reason: a per-secret `providers = [...]` override wins over
`--provider env`, so a committed override makes the manifest unresolvable
for anyone without your store — including this repository's own tests,
which verify scopes against the dummy `env` provider.

### Reasons are mandatory

SecretSpec requires an access reason by default (`require_reason`,
defaulting to `"agents"`), so a bare `secretspec run` is refused:

```
Accessing secrets requires a reason. Provide one with --reason "<why you
are accessing these secrets>" …
```

The `yacht-run-*` wrappers always pass one, naming the scope and the
command. Keep that habit in ad-hoc invocations — the reason is what shows
up in the audit log next to the access.

## Running Yacht with a scoped secret

The contributor environment (`devenv.nix`) provides two scripts. Each one
selects exactly one scope, records an audit reason, and injects the
matching `--secret` reference:

```sh
yacht-run-anthropic examples/custom-eval-skill-ab-smoke.toml \
  --logbook /private/tmp/yacht-run \
  --workspace .

yacht-run-openai examples/custom-eval-codex-skill-ab-smoke.toml \
  --logbook /private/tmp/yacht-run \
  --workspace .
```

`yacht-run-anthropic` expands to:

```sh
secretspec run --scope anthropic \
  --reason "Yacht agent operation: uv run yacht run (scope anthropic)" \
  -- uv run --locked yacht run "$@" \
       --secret anthropic=@env:ANTHROPIC_API_KEY
```

What a scope buys: `secretspec run --scope anthropic` resolves
`ANTHROPIC_API_KEY` and *removes* every other manifest-declared secret
from the child environment — including one the parent shell already
exported. So the Yacht process, the harness it launches, and every
container it starts see one key instead of all of them.

What a scope does not buy: it narrows *delivery*, not *authorization*.
The provider session that answered the first prompt is still valid, so a
process inside the scoped command could resolve a different scope by
asking SecretSpec again. Scopes reduce blast radius; provider-side spend
limits and revocable keys are what bound it.

For any other Yacht command, use the explicit form:

```sh
secretspec run --scope anthropic \
  --reason "Yacht agent operation" \
  -- uv run yacht internals preflight <config> \
       --logbook "$LOGBOOK" --workspace . \
       --secret anthropic=@env:ANTHROPIC_API_KEY
```

A config that needs two providers at once (for example an OMP-vs-Codex
comparison) cannot use a single scope. Resolve the whole default profile
for that one command instead, and pass both references:

```sh
secretspec run --reason "Yacht two-provider comparison" \
  -- uv run yacht run <config> --logbook "$LOGBOOK" --workspace . \
       --secret anthropic=@env:ANTHROPIC_API_KEY \
       --secret openai=@env:OPENAI_API_KEY
```

## Human workflow

1. `devenv shell` (or `direnv allow` once). No secrets are loaded here —
   `devenv.yaml` sets `secretspec: enable: false`, so entering the shell
   never contacts a provider and never populates an API key.
2. Work, run gates: `yacht-check`, `yacht-test`, `yacht-lint`,
   `yacht-compile`.
3. For a live run, use `yacht-run-anthropic` / `yacht-run-openai`.
   Approve the provider prompt when it appears.

With 1Password, authorization typically stays valid for the rest of the
terminal session: the first `yacht-run-anthropic` prompts, later ones in
the same session usually do not. Treat the session, not the individual
command, as the thing you authorized — if you walk away from an
authorized terminal, an agent working in it can resolve that scope again
without a new prompt.

## Coding-agent workflow

An agent working in this repository must **announce the exact scope and
the exact Yacht command before triggering a live provider access**, and
wait for the operator to approve the prompt. For example:

> About to run scope `anthropic` with:
> `yacht-run-anthropic examples/custom-eval-skill-ab-smoke.toml --logbook /private/tmp/yacht-run --workspace .`
> This will trigger a 1Password prompt. Approve?

This is a working agreement that keeps spend and credential use visible.
It is not a sandbox boundary: an agent that can run `yacht-run-anthropic`
can also run `secretspec run` directly, and a still-authorized 1Password
session will not stop it. The protections that hold regardless are the
provider-side ones below.

Also required of agents (and good practice for humans):

- Run every non-secret check first — tests, lint, `devenv` evaluation,
  `nix flake check`. Live provider access is the last step, not the
  first.
- Never print a resolved value.

## Things not to do

- **`secretspec get`** and **`secretspec export`** print values to a
  terminal, which puts them in scrollback, transcripts, and agent
  context. Use `secretspec run` and `secretspec check`.
- **Environment dumps** — `env`, `printenv`, `set`,
  `os.environ` dumps in a debug print — inside a scoped command. The
  whole point of the scope is that only one key is present; do not paste
  it somewhere else.
- **Shell tracing** (`set -x`, `bash -x`) around a scoped command: the
  trace expands resolved variables.
- **`--secret name=value`** with a literal value. It lands in shell
  history, `ps` output, CI logs, and any transcript of the session. Yacht
  supports literals for tests and CI systems that inject values another
  way; for interactive use, always `@env:`.
- **Committing** `.env` files, provider URIs with vault/item/field names,
  or a personal SecretSpec global configuration.

## Use dedicated, revocable keys

Use an API key created for Yacht evaluation and nothing else:

- one key per operator per provider, so revoking it costs nothing else;
- a provider-side spend limit and rate limit on that key — an evaluation
  loop is exactly the workload that turns a bug into a bill;
- rotate it (`secretspec set ANTHROPIC_API_KEY`) whenever a machine, a
  terminal, or an agent session is in doubt.

A scope limits which key a command can reach. A spend limit is what
limits the damage when something reaches it anyway.

## Updating the pinned SecretSpec release

`nix/secretspec.nix` pins the SecretSpec release the contributor
environment installs, because nixpkgs trails upstream (nixpkgs shipped
0.18.0 when upstream released 0.19.1). It follows the standard nixpkgs
`buildRustPackage` + `fetchCrate` pattern, so the update is mechanical:

```sh
nix-shell -p nix-update --run \
  'nix-update --file nix/secretspec.nix --version <new-version> secretspec'
```

Or by hand:

1. check the latest release at
   <https://github.com/cachix/secretspec/releases>;
2. bump `version` in `nix/secretspec.nix`;
3. set `hash` and `cargoHash` to `lib.fakeHash`, run
   `devenv shell -- secretspec --version`, and copy each real hash out of
   the two build failures (source hash first, then vendor hash);
4. if the test fixture URL moved, refresh the `fetchurl` hash in
   `postPatch`;
5. verify: `devenv shell -- secretspec --version` and
   `uv run --locked -m unittest tests.test_secretspec_manifest`.

Once nixpkgs catches up, `nix/secretspec.nix` can be deleted and
`devenv.nix` can use `pkgs.secretspec` directly.

## Verifying the wiring without a real key

Everything above can be exercised with a dummy value and SecretSpec's
`env` provider, which reads from the environment and contacts nothing:

```sh
SECRETSPEC_PROVIDER=env ANTHROPIC_API_KEY=yacht-dummy-smoke-DO-NOT-USE \
  yacht-run-anthropic examples/memory-smoke-test.toml \
    --logbook /private/tmp/yacht-devenv-smoke
```

`tests/test_secretspec_manifest.py` does the same in the test suite, with
an isolated `HOME` so no operator-global provider configuration is
reachable, and `tests/test_secret_resolution.py` proves the scrubbing and
redaction behavior with an unmistakable dummy sentinel. No automated test
touches a real credential.
