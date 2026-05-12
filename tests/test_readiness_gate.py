import json
import tempfile
import unittest
from pathlib import Path

from tests.test_benchmark_readiness_report import _mark_baseline_ready
from tests.test_benchmark_readiness_report import _write_execution_plan
from yacht.readiness_gate import evaluate_readiness_gate


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
