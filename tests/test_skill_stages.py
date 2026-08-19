"""Skill delivery stages: vocabulary sync and what a failed read proves."""

import json
import unittest
from pathlib import Path

from yacht.contracts.json_schema import schema_text
from yacht.contracts.schemas import TASK_ATTEMPT_SCHEMA, _SKILL_STAGE_STATES
from yacht.harnesses import skill_stages
from yacht.harnesses.codex import parse_codex_jsonl
from yacht.harnesses.omp import parse_omp_jsonl


OMP_SKILL_BODY = Path("tests/fixtures/omp-skill-read.jsonl")
OMP_SKILL_UNKNOWN = Path("tests/fixtures/omp-skill-unknown.jsonl")
CODEX_SKILL_BODY = Path("tests/fixtures/codex-exec-skill.jsonl")
CODEX_SKILL_MISSING = Path("tests/fixtures/codex-exec-skill-missing.jsonl")


class SkillStageVocabularyTests(unittest.TestCase):
    def test_states_match_the_contract_validator(self) -> None:
        self.assertEqual(
            {skill_stages.OBSERVED, skill_stages.ABSENT, skill_stages.UNMEASURED},
            _SKILL_STAGE_STATES,
        )

    def test_states_match_the_task_attempt_schema_enum(self) -> None:
        schema = json.loads(schema_text(TASK_ATTEMPT_SCHEMA))
        stage = schema["$defs"]["agent"]["properties"]["skill_stages"]["items"]
        for name in ("available", "selected", "loaded"):
            with self.subTest(stage=name):
                self.assertEqual(
                    set(stage["properties"][name]["enum"]),
                    {
                        skill_stages.OBSERVED,
                        skill_stages.ABSENT,
                        skill_stages.UNMEASURED,
                    },
                )

    def test_every_outcome_emits_only_contract_states(self) -> None:
        for outcome in (
            skill_stages.LOADED,
            skill_stages.NOT_DELIVERED,
            skill_stages.ATTEMPTED,
        ):
            with self.subTest(outcome=outcome):
                stage = skill_stages.skill_stage(
                    skill="team-conventions",
                    outcome=outcome,
                    evidence_source="omp-jsonl",
                )
                states = {stage["available"], stage["selected"], stage["loaded"]}
                self.assertLessEqual(states, _SKILL_STAGE_STATES)

    def test_unknown_outcome_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported skill read outcome"):
            skill_stages.skill_stage(
                skill="team-conventions",
                outcome="delivered-probably",
                evidence_source="omp-jsonl",
            )

    def test_no_outcome_claims_availability(self) -> None:
        # Reading a body proves the body exists, not that the harness
        # advertised the skill to the model.
        for outcome in (
            skill_stages.LOADED,
            skill_stages.NOT_DELIVERED,
            skill_stages.ATTEMPTED,
        ):
            with self.subTest(outcome=outcome):
                stage = skill_stages.skill_stage(
                    skill="team-conventions",
                    outcome=outcome,
                    evidence_source="omp-jsonl",
                )
                self.assertEqual(stage["available"], skill_stages.UNMEASURED)


class FailedSkillReadTests(unittest.TestCase):
    def test_omp_errored_skill_read_is_not_loaded(self) -> None:
        # Captured shape of `skill://motif-work` answered with
        # `Unknown skill: motif-work`: isError true, and the error text
        # arrives as ordinary text content.
        parsed = parse_omp_jsonl(OMP_SKILL_UNKNOWN.read_text(encoding="utf-8"))

        assert parsed is not None
        self.assertEqual(
            parsed["skill_stages"],
            (
                {
                    "skill": "motif-work",
                    "available": "unmeasured",
                    "selected": "observed",
                    "loaded": "absent",
                    "evidence_source": "omp-jsonl",
                },
            ),
        )

    def test_omp_successful_skill_read_is_still_loaded(self) -> None:
        parsed = parse_omp_jsonl(OMP_SKILL_BODY.read_text(encoding="utf-8"))

        assert parsed is not None
        self.assertEqual(parsed["skill_stages"][0]["loaded"], "observed")

    def test_codex_failed_skill_command_does_not_claim_absence(self) -> None:
        # A nonzero exit on a command that merely mentions the skill path
        # is not evidence about the skill: it stays unmeasured.
        parsed = parse_codex_jsonl(CODEX_SKILL_MISSING.read_text(encoding="utf-8"))

        assert parsed is not None
        self.assertEqual(
            parsed["skill_stages"],
            (
                {
                    "skill": "motif-work",
                    "available": "unmeasured",
                    "selected": "observed",
                    "loaded": "unmeasured",
                    "evidence_source": "codex-jsonl",
                },
            ),
        )

    def test_codex_successful_skill_command_is_still_loaded(self) -> None:
        parsed = parse_codex_jsonl(CODEX_SKILL_BODY.read_text(encoding="utf-8"))

        assert parsed is not None
        self.assertEqual(parsed["skill_stages"][0]["loaded"], "observed")


if __name__ == "__main__":
    unittest.main()
