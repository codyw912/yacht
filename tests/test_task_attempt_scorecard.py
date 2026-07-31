import unittest

from yacht.contracts.schemas import (
    SchemaValidationError,
    validate_harness_evidence_document,
    validate_task_attempt_scorecard_document,
)
from yacht.harnesses.evidence_map import map_native_evidence
from yacht.reports.task_attempt_scorecard import (
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

        self.assertEqual(vessel["total_cost"], 0.0)
        self.assertEqual(vessel["cost_sources"], ["unreported"])

    def test_vessel_marks_reported_cost(self) -> None:
        vessel = _vessel_score(
            "candidate",
            [_full_attempt({"cost": {"total_usd": 1.5}})],
        )

        self.assertEqual(vessel["total_cost"], 1.5)
        self.assertEqual(vessel["cost_sources"], ["reported"])


def _scorecard_document(cost_sources: list[str]) -> dict:
    vessel = _vessel_score("candidate", [_full_attempt({"cost": {"total_usd": 1.5}})])
    vessel["cost_sources"] = cost_sources
    summary = {
        "total_vessels": 1,
        "total_attempts": 1,
        "completed_attempts": 1,
        "failed_attempts": 0,
        "total_tool_calls": 0,
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


if __name__ == "__main__":
    unittest.main()
