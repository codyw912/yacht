# Yacht contributor environment.
#
# This is NOT the host-nix runtime contract. `flake.nix` stays exactly as
# it is: `yacht.runtimes.host_nix` runs `nix develop <flake>#<shell>`
# against runtime flakes, and its `default` / `pi` shells are part of that
# contract. This file is only for people (and coding agents) working on
# Yacht itself.
#
# Secrets: `secretspec.enable` is false in devenv.yaml, so entering this
# shell never contacts a provider. The yacht-run-* scripts below resolve
# exactly one scope around exactly one Yacht command.
{ pkgs, ... }:

let
  # nixpkgs trails upstream SecretSpec; nix/secretspec.nix pins the
  # release this repository documents. See docs/reference/secrets.md.
  secretspec = pkgs.callPackage ./nix/secretspec.nix { };

  python = pkgs.python312;

  # Every scoped command follows the same shape: one SecretSpec scope, an
  # audited reason, `uv run yacht run`, and the matching --secret
  # reference. The value is never printed, exported, or passed as an
  # argument — only the variable *name* crosses the boundary.
  #
  # Manifest selection: the committed secretspec.toml carries declarations
  # and scopes only. An operator's provider coordinates live in an
  # uncommitted secretspec.local.toml that extends it; prefer that file
  # when present.
  scopedYachtRun =
    {
      scope,
      secretName,
      variable,
    }:
    ''
      set -euo pipefail
      root="''${DEVENV_ROOT:-$PWD}"
      manifest="$root/secretspec.toml"
      if [ -f "$root/secretspec.local.toml" ]; then
        manifest="$root/secretspec.local.toml"
      fi
      exec secretspec run \
        --file "$manifest" \
        --scope ${scope} \
        --reason "Yacht agent operation: uv run yacht run (scope ${scope})" \
        -- uv run --locked yacht run "$@" \
             --secret ${secretName}=@env:${variable}
    '';
in
{
  packages = [
    pkgs.git
    pkgs.uv
    secretspec
  ];

  languages.python.enable = true;
  languages.python.package = python;

  # Keep `uv run` on the interpreter this environment pins instead of
  # letting uv download a second CPython 3.12.
  env.UV_PYTHON = "${python}/bin/python3.12";

  scripts = {
    # --- repository gates (same commands CI runs) ---------------------
    yacht-test.exec = ''
      set -euo pipefail
      exec uv run --locked -m unittest discover -s tests "$@"
    '';
    yacht-lint.exec = ''
      set -euo pipefail
      exec ./scripts/lint.sh
    '';
    yacht-compile.exec = ''
      set -euo pipefail
      exec uv run --locked -m compileall src tests
    '';
    yacht-check.exec = ''
      set -euo pipefail
      uv sync --locked
      ./scripts/lint.sh
      uv run --locked -m unittest discover -s tests
      uv run --locked -m compileall src tests
    '';

    # --- scoped live runs --------------------------------------------
    # Usage:
    #   yacht-run-anthropic examples/custom-eval-skill-ab-smoke.toml \
    #     --logbook /private/tmp/yacht-run --workspace .
    yacht-run-anthropic.exec = scopedYachtRun {
      scope = "anthropic";
      secretName = "anthropic";
      variable = "ANTHROPIC_API_KEY";
    };
    yacht-run-openai.exec = scopedYachtRun {
      scope = "openai";
      secretName = "openai";
      variable = "OPENAI_API_KEY";
    };
  };

  enterShell = ''
    echo "yacht contributor shell: python $(python3 --version 2>&1 | cut -d' ' -f2), uv $(uv --version | cut -d' ' -f2), $(secretspec --version)"
    echo "gates:      yacht-check | yacht-test | yacht-lint | yacht-compile"
    echo "live runs:  yacht-run-anthropic <config> [args] | yacht-run-openai <config> [args]"
    echo "secrets:    not loaded here; see docs/reference/secrets.md"
  '';
}
