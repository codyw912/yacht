# Contributing

## Testing Conventions

Three rules, each earned by a bug that reached a live run:

- **Changing a shared seam means testing every caller.** When a
  function serving multiple course kinds or artifact writers gains new
  behavior (especially validation), enumerate its callers and make
  sure a test exercises the change through each one — through the
  registry, the way production reaches it, not only against
  hand-built fixtures. `tests/test_course_grading_roundtrips.py` is
  the pattern.
- **Derive contract vocabularies from the registry that owns them.**
  A set of allowed values hand-copied from another module is a latent
  divergence, not a constant (`COURSE_GRADING_SCHEMAS` and
  `COURSE_ADAPTER_KINDS` are derived for this reason). Where a direct
  import would cycle, pin the literal and add a sync test.
- **Every validate-on-write seam gets a zero-token roundtrip test**:
  the writer's own output must pass its own validator, per registered
  caller. Live token-spending runs are the last line of verification
  for what unit tests cannot reach (real harness rendering, real
  transcripts) — never the first line for schema plumbing.

## Adding a Benchmark Course

The most valuable contribution is a new course. The contract — adapter
interfaces, artifact shapes, pinning and trust rules, and the quality bar
a course PR must meet — is documented in
[Adding a Course](docs/reference/adding-a-course.md).

## License

By contributing to YACHT, you agree that your contribution is licensed under the
Apache License 2.0, the same license as the project, unless you explicitly mark
the contribution as "Not a Contribution."

## Local Checks

Run the same checks that CI runs:

```sh
uv sync --locked
./scripts/lint.sh
uv run --locked -m unittest discover -s tests
uv run --locked -m compileall src tests
uv run --locked yacht validate examples/container-pi-fff-real-benchmark-smoke.toml
uv run --locked yacht run examples/memory-smoke-test.toml --logbook /tmp/yacht-smoke-local
```

`scripts/lint.sh` is the same `ruff check` and `ruff format --check`
CI runs before tests. Run it before `jj git push`; jj does not invoke
Git hooks.

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
