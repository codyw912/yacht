# ADR 0007: Publish the Distribution as yacht-eval

## Status

Accepted

## Context

The PyPI project name `yacht` is occupied by an unrelated YAML-to-HTML
converter whose last release was 2024-03-02, whose repository has been
inactive since 2024-03-15, and whose download volume is consistent with
mirror traffic rather than users. A voluntary-transfer request to its author
and, failing that, a PEP 541 claim are being pursued, but PEP 541 review
commonly takes months and must not gate the 0.1 release.

PyPI also permanently forbids reusing uploaded file names: the existing
package published versions 0.0.2 through 0.4.4, so even a successful name
transfer would prevent this project from ever publishing `yacht 0.1.0`.

The distribution name is independent of the import package and the console
script, which can both remain `yacht` regardless of what the distribution is
called.

## Decision

We will publish to PyPI as `yacht-eval`, keeping `yacht` as the import
package name and the console-script name. We will reserve the `yacht-eval`
name promptly with a real early release rather than waiting for 0.1.

If the PEP 541 claim or a voluntary transfer later grants the `yacht` name,
we will begin publishing there at a version above the prior occupant's 0.4.4
(planned: 1.0.0) and keep `yacht-eval` as a deprecated alias that depends on
`yacht`.

## Consequences

- The 0.1 release is not blocked on an external process with an unbounded
  timeline.
- `uv run yacht`, `import yacht`, and all documentation of the command name
  stay as they are; only install instructions say `yacht-eval`.
- The install-name/command-name mismatch is a small permanent documentation
  cost unless the transfer succeeds.
- If the transfer succeeds, the version jump to 1.0.0 avoids collision with
  the prior occupant's file names, and existing `yacht-eval` users migrate
  through the alias rather than breaking.
