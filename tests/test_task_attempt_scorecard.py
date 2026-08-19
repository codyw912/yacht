import json
import tempfile
import unittest
from pathlib import Path

from yacht.contracts.schemas import (
    SchemaValidationError,
    validate_harness_evidence_document,
    validate_task_attempt_scorecard_document,
)
from yacht.harnesses.evidence_map import map_native_evidence
from yacht.reports.task_attempt_scorecard import (
    normalize_task_attempt_scorecard,
    _attempt_cost,
    _attempt_cost_source,
    _vessel_score,
)


def _mapped_evidence(cost: float) -> dict:
    """Evidence produced by the ADR 0017 mapping path, schema-validated."""
    evidence = map_native_evidence(
        {
            "response": "response.text",
            "input_tokens": "usage.in",
            "output_tokens": "usage.out",
            "cost_usd": "usage.cost",
        },
        {
            "response": {"text": "done"},
            "usage": {"in": 100, "out": 50, "cost": cost},
        },
    )
    validate_harness_evidence_document(evidence)
    return evidence


def _attempt(machine_evidence: dict) -> dict:
    return {"agent": {"machine_evidence": machine_evidence}}


def _full_attempt(machine_evidence: dict) -> dict:
    """A task attempt with the fields the vessel scorer reads."""
    return {
        "status": "completed",
        "metrics": {"tokens": 10, "duration_seconds": 1.0},
        "runtime_context": {"harness": "declared-harness"},
        "artifact_path": "/tmp/attempt.json",
        "agent": {"tool_calls": [], "machine_evidence": machine_evidence},
    }


class AttemptCostTests(unittest.TestCase):
    def test_declared_harness_cost_is_not_lost(self) -> None:
        # The mapping path emits cost.total_usd — the name the harness
        # evidence schema requires — while built-in adapters emit
        # cost.total. Spend must survive either spelling.
        evidence = _mapped_evidence(4.25)
        self.assertEqual(evidence["cost"], {"total_usd": 4.25})

        attempt = _attempt({"format": "yacht-harness-evidence", **evidence})

        self.assertEqual(_attempt_cost(attempt), 4.25)

    def test_builtin_harness_cost_is_still_read(self) -> None:
        attempt = _attempt(
            {"format": "claude-code-stream-json", "cost": {"total": 4.25}}
        )

        self.assertEqual(_attempt_cost(attempt), 4.25)


class CostProvenanceTests(unittest.TestCase):
    def test_reported_zero_is_distinguishable_from_no_report(self) -> None:
        # tokens already carry usage_source; cost carried nothing, so a
        # total_cost of 0.0 could mean "free" or "nobody told us".
        reported = _attempt({"cost": {"total_usd": 0.0}})
        silent = _attempt({"format": "yacht-harness-evidence"})

        self.assertEqual(_attempt_cost_source(reported), "reported")
        self.assertEqual(_attempt_cost_source(silent), "unreported")

    def test_vessel_records_whether_cost_was_reported_at_all(self) -> None:
        vessel = _vessel_score(
            "candidate",
            [
                _full_attempt({"format": "yacht-harness-evidence"}),
                _full_attempt({"format": "yacht-harness-evidence"}),
            ],
        )

        self.assertIsNone(vessel["total_cost"])
        self.assertEqual(vessel["cost_sources"], ["unreported"])

    def test_vessel_marks_reported_cost(self) -> None:
        vessel = _vessel_score(
            "candidate",
            [_full_attempt({"cost": {"total_usd": 1.5}})],
        )

        self.assertEqual(vessel["total_cost"], 1.5)
        self.assertEqual(vessel["cost_sources"], ["reported"])

    def test_vessel_total_is_unknown_when_any_attempt_omits_cost(self) -> None:
        vessel = _vessel_score(
            "candidate",
            [
                _full_attempt({"cost": {"total_usd": 1.5}}),
                _full_attempt({"format": "yacht-harness-evidence"}),
            ],
        )

        self.assertIsNone(vessel["total_cost"])
        self.assertEqual(vessel["cost_sources"], ["reported", "unreported"])


def _scorecard_document(cost_sources: list[str]) -> dict:
    vessel = _vessel_score("candidate", [_full_attempt({"cost": {"total_usd": 1.5}})])
    vessel["cost_sources"] = cost_sources
    summary = {
        "total_vessels": 1,
        "total_attempts": 1,
        "completed_attempts": 1,
        "failed_attempts": 0,
        "total_distinct_tool_uses": 0,
        "total_tokens": 10,
        "total_duration_seconds": 1.0,
    }
    return {
        "schema": "yacht.task-attempt-scorecard.v1",
        "regatta": "r",
        "course": "c",
        "status": "complete",
        "summary": {"total_comparisons": 1, **summary},
        "comparisons": [{"name": "cmp", "summary": summary, "vessels": [vessel]}],
    }


class CostSourceContractTests(unittest.TestCase):
    def test_reported_and_unreported_are_accepted(self) -> None:
        validate_task_attempt_scorecard_document(_scorecard_document(["reported"]))
        validate_task_attempt_scorecard_document(_scorecard_document(["unreported"]))

    def test_an_invented_cost_source_is_rejected(self) -> None:
        with self.assertRaises(SchemaValidationError):
            validate_task_attempt_scorecard_document(_scorecard_document(["estimated"]))


def _attempt_using(tools: list[str]) -> dict:
    attempt = _full_attempt({})
    attempt["agent"]["tool_calls"] = tools
    return attempt


class ToolUseNamingTests(unittest.TestCase):
    def test_the_count_is_named_for_what_it_measures(self) -> None:
        # Producers deduplicate tool names, so an attempt that called
        # Bash fifty times and Read once records two entries. The field
        # must not be named for calls it never counted.
        vessel = _vessel_score(
            "candidate",
            [_attempt_using(["Bash", "Read"]), _attempt_using(["Bash", "Read"])],
        )

        self.assertEqual(vessel["distinct_tool_uses"], 4)
        self.assertNotIn("tool_call_count", vessel)

    def test_per_tool_counts_are_named_for_attempts(self) -> None:
        vessel = _vessel_score(
            "candidate",
            [_attempt_using(["Bash", "Read"]), _attempt_using(["Bash"])],
        )

        self.assertEqual(vessel["attempts_by_tool"], {"Bash": 2, "Read": 1})
        self.assertNotIn("tool_call_counts", vessel)


class EpisodesOutcomeCountingTests(unittest.TestCase):
    def test_an_episodes_block_does_not_change_outcome_counting(self) -> None:
        # ADR 0025: a relay task's episodes are sub-steps within one trial,
        # not additional trials. The scorer counts attempts, not episodes —
        # pin that an "episodes" block leaves outcome counting untouched.
        episodic = _full_attempt({})
        episodic["episodes"] = {
            "count": 2,
            "to_resolution": 2,
            "items": [
                {"index": 1, "ended": "cap"},
                {"index": 2, "ended": "natural", "reward": 1.0},
            ],
        }
        plain = _full_attempt({})

        episodic_vessel = _vessel_score("candidate", [episodic])
        plain_vessel = _vessel_score("candidate", [plain])

        for key in (
            "task_attempts",
            "completed_attempts",
            "failed_attempts",
            "success_rate",
        ):
            self.assertEqual(episodic_vessel[key], plain_vessel[key])


LEGACY_VESSEL_KEYS = ("tool_call_count", "tool_call_counts")


def _legacy_scorecard() -> dict:
    """A scorecard as written before the fields were renamed."""
    document = _scorecard_document(["reported"])
    for comparison in document["comparisons"]:
        for vessel in comparison["vessels"]:
            vessel["tool_call_count"] = vessel.pop("distinct_tool_uses")
            vessel["tool_call_counts"] = vessel.pop("attempts_by_tool")
        comparison["summary"]["total_tool_calls"] = comparison["summary"].pop(
            "total_distinct_tool_uses"
        )
    document["summary"]["total_tool_calls"] = document["summary"].pop(
        "total_distinct_tool_uses"
    )
    return document


class LegacyToolFieldTests(unittest.TestCase):
    def test_a_pre_rename_scorecard_still_validates(self) -> None:
        # Logbooks written before the rename must keep working:
        # recorded baselines and repetition aggregates read them.
        validate_task_attempt_scorecard_document(_legacy_scorecard())

    def test_normalizing_exposes_the_new_names(self) -> None:
        normalized = normalize_task_attempt_scorecard(_legacy_scorecard())

        vessel = normalized["comparisons"][0]["vessels"][0]
        self.assertEqual(vessel["distinct_tool_uses"], 0)
        self.assertEqual(vessel["attempts_by_tool"], {})
        self.assertNotIn("tool_call_count", vessel)
        self.assertIn(
            "total_distinct_tool_uses",
            normalized["comparisons"][0]["summary"],
        )


class LegacyLogbookReaderTests(unittest.TestCase):
    def test_report_loader_upgrades_a_pre_rename_scorecard(self) -> None:
        # Validating a normalized copy is not enough: readers receive the
        # loaded document, and indexing a renamed field on a legacy
        # logbook crashed the CLI even while the unit tests passed.
        from yacht.reports.benchmark_report import _load_task_attempt_scorecard

        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = Path(temp_dir)
            (logbook / "task-attempt-scorecard.json").write_text(
                json.dumps(_legacy_scorecard()), encoding="utf-8"
            )

            loaded = _load_task_attempt_scorecard(logbook)

            assert loaded is not None
            self.assertIn("total_distinct_tool_uses", loaded["summary"])
            vessel = loaded["comparisons"][0]["vessels"][0]
            self.assertIn("distinct_tool_uses", vessel)
            self.assertNotIn("tool_call_count", vessel)


if __name__ == "__main__":
    unittest.main()
