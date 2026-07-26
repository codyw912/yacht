# Release Checklist

Use this checklist before tagging a YACHT release.

## Metadata

- Confirm `pyproject.toml` and `src/yacht/__init__.py` have the intended
  version.
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
uv run --isolated --no-project --with ./dist/yacht_eval-0.6.0-py3-none-any.whl yacht validate examples/container-pi-fff-real-benchmark-smoke.toml
uv run --isolated --no-project --with ./dist/yacht_eval-0.6.0-py3-none-any.whl yacht run examples/memory-smoke-test.toml --logbook /tmp/yacht-wheel-smoke
```

Update the wheel filename when the release version changes.

## Publish

Publishing runs through PyPI trusted publishing: pushing a `v<version>` tag
triggers `.github/workflows/workflow.yml`, which re-runs the test suite,
verifies the tag matches the project version, builds, and uploads via OIDC.
No PyPI token is stored anywhere.

```sh
git tag v<version> <main commit>
git push origin v<version>
```

Tag the merge commit on main whose version matches the tag; the workflow
fails if they disagree.

## Optional Real Smoke

Run this only when you intend to spend provider tokens and have the Pi runtime
image built locally.

```sh
LOGBOOK=/private/tmp/yacht-real-benchmark-$(date +%Y%m%d-%H%M%S)

uv run yacht run examples/container-pi-fff-real-benchmark-smoke.toml \
  --logbook "$LOGBOOK" \
  --workspace . \
  --secret anthropic=@env:ANTHROPIC_API_KEY

uv run yacht status --logbook "$LOGBOOK"
uv run yacht report --logbook "$LOGBOOK"
```
