"""Delivery stages for a skill the agent tried to read.

A stage answers one question with one of three states: ``observed`` (we
saw it), ``absent`` (we looked and it was not there), ``unmeasured`` (the
stream cannot tell us). The states are pinned by
``yacht.contracts.schemas._SKILL_STAGE_STATES`` and by
``schemas/yacht.task-attempt.v1.schema.json``;
``tests/test_skill_stages.py`` keeps this module in sync with them.

The distinction that matters: a failed read is evidence, not silence. An
agent that asks for ``skill://motif-work`` and gets an error back has not
loaded anything, and must never be reported as ``loaded`` merely because
the harness returned some text — an error message is text too. That is how
a missing treatment starts looking like a delivered one.

The symmetric mistake is to read too much into a failure. An errored read
proves the body did not arrive (``loaded`` is ``absent``); it does not say
why, so ``available`` stays ``unmeasured``. Only a signal that names the
skill as unresolvable could establish absence, and neither OMP's
``isError`` flag nor a shell exit code is that signal: a nonzero exit may
come from permissions or from a later clause of a compound command that
never reflects on whether the skill exists.
"""

from __future__ import annotations

OBSERVED = "observed"
ABSENT = "absent"
UNMEASURED = "unmeasured"

#: The read returned the skill body: the agent selected it and loaded it.
LOADED = "loaded"
#: The read completed without delivering a body: measured non-delivery.
NOT_DELIVERED = "not-delivered"
#: The read was issued but the stream does not say how it ended.
ATTEMPTED = "attempted"

_STAGES_BY_OUTCOME = {
    # `available` stays unmeasured even on success: reading a skill body
    # proves the body exists, not that the harness advertised the skill to
    # the model, which is what availability claims.
    LOADED: (UNMEASURED, OBSERVED, OBSERVED),
    NOT_DELIVERED: (UNMEASURED, OBSERVED, ABSENT),
    ATTEMPTED: (UNMEASURED, OBSERVED, UNMEASURED),
}


def skill_stage(*, skill: str, outcome: str, evidence_source: str) -> dict[str, str]:
    """Build one skill-stage record from a read outcome."""
    if outcome not in _STAGES_BY_OUTCOME:
        raise ValueError(f"unsupported skill read outcome {outcome}")
    available, selected, loaded = _STAGES_BY_OUTCOME[outcome]
    return {
        "skill": skill,
        "available": available,
        "selected": selected,
        "loaded": loaded,
        "evidence_source": evidence_source,
    }
