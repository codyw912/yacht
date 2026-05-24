import json
import tempfile
import unittest
from pathlib import Path

from tests.test_benchmark_readiness_report import _mark_baseline_ready
from tests.test_benchmark_readiness_report import _write_execution_plan
from yacht.workflows.benchmark_execution_plan import BENCHMARK_EXECUTION_PLAN_PATH
from yacht.workflows.readiness_gate import evaluate_readiness_gate
from yacht.domain.model import ConfigError


class ReadinessGateTests(unittest.TestCase):
    def test_evaluate_readiness_gate_reports_blocked_vessels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_execution_plan(logbook_dir)

            gate = evaluate_readiness_gate(logbook_dir)

            self.assertEqual(gate.exit_code, 1)
            self.assertEqual(gate.blocked_vessel_count, 1)
            self.assertEqual(gate.summary["blocked_vessel_count"], 1)
            self.assertEqual(json.loads(gate.summary_json), gate.summary)

    def test_evaluate_readiness_gate_passes_without_blocked_vessels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_execution_plan(logbook_dir)
            _mark_baseline_ready(logbook_dir)

            gate = evaluate_readiness_gate(logbook_dir)

            self.assertEqual(gate.exit_code, 0)
            self.assertEqual(gate.blocked_vessel_count, 0)
            self.assertEqual(gate.summary["launchable_vessels"], 1)

    def test_evaluate_readiness_gate_rejects_missing_execution_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"

            with self.assertRaisesRegex(
                ConfigError,
                "benchmark execution plan artifact not found:",
            ):
                evaluate_readiness_gate(logbook_dir)

    def test_evaluate_readiness_gate_rejects_invalid_execution_plan_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH).write_text(
                "{not json",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ConfigError,
                "benchmark execution plan artifact is not valid JSON:",
            ):
                evaluate_readiness_gate(logbook_dir)

    def test_evaluate_readiness_gate_rejects_invalid_execution_plan_schema(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            logbook_dir.mkdir()
            (logbook_dir / BENCHMARK_EXECUTION_PLAN_PATH).write_text(
                json.dumps({"schema": "yacht.benchmark-execution-plan.v1"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ConfigError,
                "benchmark execution plan artifact is invalid:",
            ):
                evaluate_readiness_gate(logbook_dir)
