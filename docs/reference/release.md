# Release Checklist

Use this checklist before tagging a YACHT release.

## Metadata

- Confirm `pyproject.toml` and `src/yacht/__init__.py` have the intended
  version, then run `uv lock` so the lockfile records it (`--locked`
  steps below fail otherwise).
- Confirm `CHANGELOG.md` has an entry for the release.
- Confirm the README first-run path matches the current CLI.

## Local Verification

```sh
uv sync --locked
uv run --locked -m unittest discover -s tests
uv run --locked -m compileall src tests
uv run --locked yacht validate examples/container-pi-fff-real-benchmark-smoke.toml
uv run --locked yacht validate examples/container-pi-fff-real-benchmark-small.toml
uv run --locked yacht run examples/memory-smoke-test.toml --logbook /tmp/yacht-release-smoke
```

## Package Build

The PyPI distribution is named `yacht-eval`; the import package and console
script stay `yacht` (see ADR 0007).

```sh
uv build
uv run --isolated --no-project --with ./dist/yacht_eval-0.11.0-py3-none-any.whl yacht validate examples/container-pi-fff-real-benchmark-smoke.toml
uv run --isolated --no-project --with ./dist/yacht_eval-0.11.0-py3-none-any.whl yacht run examples/memory-smoke-test.toml --logbook /tmp/yacht-wheel-smoke
```

Update the wheel filename when the release version changes.

## Publish

Publishing runs through PyPI trusted publishing: pushing a `v<version>` tag
triggers `.github/workflows/workflow.yml`, which re-runs the test suite,
verifies the tag matches the project version, builds, and uploads via OIDC.
No PyPI token is stored anywhere.

```sh
git tag -a v<version> -m "YACHT <version> - <release title>" <main commit>
git push origin v<version>
```

The tag must be annotated: `tag.gpgsign` is on, so a lightweight
`git tag v<version>` fails with "no tag message?". Tag the merge commit
on main whose version matches the tag; the workflow fails if they
disagree.

After the workflow publishes, create the GitHub release object — the
tag alone does not appear on the Releases page (v0.8.0 shipped without
one for three days before anyone noticed):

```sh
gh release create v<version> --verify-tag --title "YACHT <version>" \
  --notes-file <file with the CHANGELOG section for this version>
```

## Live Gate

Every release is gated on one live, token-spending run. Unit tests cover
the pieces; this proves the end-to-end provider path and the evidence
surfaces a release is judged on.

```sh
uv run python scripts/release_gate.py
```

Requires Docker, the pinned launcher image
(`docker build -t yacht/harbor-launcher:harbor-0.20.0 containers/harbor-launcher`),
and `ANTHROPIC_API_KEY`. It spends roughly $0.05: the skill A/B runs once
in full, then once more as a candidate against the first run recorded as
a baseline — the cheapest full exercise of the pipeline, and the
regression-check workflow itself.

The gate prints a pass/fail line per check and the actual provider spend,
and exits non-zero if any check fails:

- the full A/B measured both vessels;
- skill delivery was measured from preserved transcripts;
- the recorded baseline was reused, with only the live vessel running;
- paired statistics, evidence grade, and a repetition budget are present;
- the Every Eval Ever export wrote documents at the pinned schema version;
- the HTML report renders the decision metrics.

Artifacts land under a timestamped root. To re-check a finished gate
without spending again:

```sh
uv run python scripts/release_gate.py --skip-live --root <previous root>
```

A failing check means the release does not ship until it is explained.
Prefer fixing the cause over widening the gate.
