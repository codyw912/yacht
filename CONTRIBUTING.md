# Contributing

## License

By contributing to YACHT, you agree that your contribution is licensed under the
Apache License 2.0, the same license as the project, unless you explicitly mark
the contribution as "Not a Contribution."

## Local Checks

Run the same checks that CI runs:

```sh
uv sync --locked
uv run --locked -m unittest discover -s tests
uv run --locked -m compileall src tests
uv run --locked yacht validate examples/container-pi-fff-real-benchmark-smoke.toml
uv run --locked yacht real-benchmark-runbook examples/container-pi-fff-real-benchmark-smoke.toml --logbook /tmp/yacht-runbook-local --workspace . --format markdown
```

## PR Workflow

Once a remote is configured, use short-lived branches and pull requests for changes:

1. Create a branch from `main`.
2. Keep each change focused on one concern.
3. Run the local checks before opening a PR.
4. Fill in the PR summary and verification notes.
5. Merge after CI passes.

Branch protection is worth enabling once the remote exists:

- require the `CI / Test` check before merging
- require branches to be up to date before merging
- prevent direct pushes to `main` once PRs become the default
