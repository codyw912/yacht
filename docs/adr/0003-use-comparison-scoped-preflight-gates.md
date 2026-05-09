# ADR 0003: Use Comparison-Scoped Preflight Gates

## Status

Accepted

## Context

YACHT needs to verify that an evaluated runtime and its rigging are actually
available, configured, and isolated before spending benchmark-task tokens. Agent
attestation is not enough: preflight must produce machine-readable evidence such
as command results, resolved environment variables, isolated paths, and tool-call
or transcript evidence when the agent-facing integration is part of the claim.

The first target comparison is Pi baseline versus Pi+fff. Running the baseline
when the Pi+fff vessel fails preflight does not produce a useful comparison
during early development and may waste model tokens. Later publication-oriented
studies may use larger sample sizes, but LLM task outcomes should still be
treated as observations rather than deterministic cacheable results.

## Decision

YACHT will model preflight as a trust gate before task execution.

The default preflight failure policy is `abort-group`: if any required preflight
check fails for a vessel in a comparison group, YACHT should skip task execution
for that whole comparison group and write preflight evidence explaining why.

Regatta configuration may define:

- a regatta-level preflight failure policy
- runtime preflight checks
- rigging preflight checks
- named comparison groups

Preflight evidence is recorded separately from benchmark outcomes. A vessel that
fails required preflight is invalid for that comparison, not a benchmark failure.

## Consequences

YACHT avoids spending task-run tokens on comparison groups that cannot produce a
trustworthy paired result. Baseline-only or matrix-style exploratory runs can use
other policies later, such as `skip-vessel` or `abort-regatta`.

The model leaves room for future study-scale runs and non-benchmark evaluators:
preflight decides whether an observation is valid to run, while evaluators later
decide how to judge the produced artifact.
