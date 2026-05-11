import json
import tempfile
import unittest
from pathlib import Path

from tests.benchmark_fixtures import write_pi_fff_config
from tests.benchmark_fixtures import write_runtime_snapshot
from yacht.regatta import ConfigError
from yacht.runtime_instances import RUNTIME_INSTANCES_PLAN_PATH
from yacht.runtime_snapshot_gate import RuntimeSnapshotGate
from yacht.runtime_snapshot_gate import runtime_snapshot_gate


class RuntimeSnapshotGateTests(unittest.TestCase):
    def test_runtime_snapshot_gate_reports_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"

            gate = _gate(logbook_dir)

            self.assertEqual(
                gate.artifact_path,
                logbook_dir / RUNTIME_INSTANCES_PLAN_PATH,
            )
            self.assertFalse(gate.artifact_present)
            self.assertEqual(gate.status, "missing")
            self.assertFalse(gate.matched)

    def test_runtime_snapshot_gate_matches_valid_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            write_pi_fff_config(config_path)
            write_runtime_snapshot(
                config_path=config_path,
                logbook_dir=logbook_dir,
                workspace_path=root / "workspace",
            )

            gate = _gate(logbook_dir)

            self.assertTrue(gate.artifact_present)
            self.assertEqual(gate.status, "matched")
            self.assertTrue(gate.matched)

    def test_runtime_snapshot_gate_rejects_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_snapshot_text(logbook_dir, "{")

            with self.assertRaisesRegex(
                ConfigError,
                "runtime instances artifact is not valid JSON",
            ):
                _gate(logbook_dir)

    def test_runtime_snapshot_gate_rejects_json_array(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_snapshot_text(logbook_dir, "[]")

            with self.assertRaisesRegex(
                ConfigError,
                "runtime instances artifact must be a JSON object",
            ):
                _gate(logbook_dir)

    def test_runtime_snapshot_gate_rejects_schema_invalid_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            _write_snapshot_json(
                logbook_dir,
                {
                    "schema": "yacht.runtime-instances.v1",
                    "regatta": "pi-fff-comparison",
                    "course": "swe-bench-lite",
                    "mode": "dry-run",
                    "comparisons": [],
                },
            )

            with self.assertRaisesRegex(
                ConfigError,
                "runtime instances artifact is invalid: .*workspace_path is required",
            ):
                _gate(logbook_dir)


def _gate(logbook_dir: Path) -> RuntimeSnapshotGate:
    return runtime_snapshot_gate(
        logbook_dir=logbook_dir,
        regatta_name="pi-fff-comparison",
        course_name="swe-bench-lite",
        comparison_name="pi-vs-pi-fff",
        vessel_name="pi-plus-fff",
    )


def _write_snapshot_json(logbook_dir: Path, payload: object) -> None:
    _write_snapshot_text(logbook_dir, json.dumps(payload))


def _write_snapshot_text(logbook_dir: Path, payload: str) -> None:
    logbook_dir.mkdir(parents=True, exist_ok=True)
    (logbook_dir / RUNTIME_INSTANCES_PLAN_PATH).write_text(payload, encoding="utf-8")
