import json
import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import ConfigError
from yacht.logbook.index import (
    RUN_INDEX_PATH,
    LogbookState,
    read_logbook,
    require_logbook,
    write_run_index,
)


class LogbookIndexTests(unittest.TestCase):
    def test_writes_run_index_with_artifact_presence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "regatta.toml"
            logbook_dir = root / "logbook"
            (logbook_dir / "preflight").mkdir(parents=True)
            config_path.write_text('[regatta]\nname = "demo"\n', encoding="utf-8")
            (logbook_dir / "preflight-evidence-report.json").write_text(
                json.dumps({"status": "ready"}),
                encoding="utf-8",
            )

            index = write_run_index(
                logbook_dir=logbook_dir,
                config_path=config_path,
                run_kind="real-benchmark",
                status="complete",
                regatta="demo-regatta",
                course="demo-course",
                comparisons=(
                    {
                        "name": "demo-comparison",
                        "course": "demo-course",
                        "vessels": ("baseline", "challenger"),
                    },
                ),
                artifacts={
                    "preflight_evidence_report": "preflight-evidence-report.json",
                    "benchmark_scorecard": "benchmark-scorecard.json",
                },
            )

            self.assertEqual(index["schema"], "yacht.run-index.v1")
            self.assertEqual(index["run_kind"], "real-benchmark")
            self.assertEqual(index["status"], "complete")
            self.assertEqual(index["config_path"], str(config_path))
            self.assertEqual(index["logbook"], str(logbook_dir))
            self.assertEqual(index["regatta"], "demo-regatta")
            self.assertEqual(index["course"], "demo-course")
            self.assertEqual(
                index["comparisons"],
                [
                    {
                        "name": "demo-comparison",
                        "course": "demo-course",
                        "vessels": ["baseline", "challenger"],
                    }
                ],
            )
            self.assertRegex(index["updated_at"], r"^\d{4}-\d{2}-\d{2}T")
            self.assertEqual(
                index["artifacts"],
                {
                    "preflight_evidence_report": {
                        "path": str(logbook_dir / "preflight-evidence-report.json"),
                        "present": True,
                    },
                    "benchmark_scorecard": {
                        "path": str(logbook_dir / "benchmark-scorecard.json"),
                        "present": False,
                    },
                },
            )
            self.assertEqual(
                json.loads((logbook_dir / RUN_INDEX_PATH).read_text(encoding="utf-8")),
                index,
            )

    def test_refuses_to_write_an_invalid_run_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = root / "logbook"

            with self.assertRaisesRegex(ValueError, "regatta"):
                write_run_index(
                    logbook_dir=logbook_dir,
                    config_path=root / "regatta.toml",
                    run_kind="real-benchmark",
                    status="complete",
                    regatta="",
                    course="demo-course",
                    comparisons=(),
                    artifacts={},
                )

            self.assertFalse((logbook_dir / RUN_INDEX_PATH).exists())

    def test_reads_current_index_identity_lifecycle_and_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = Path(temp_dir) / "logbook"
            (logbook / "runs" / "run-1").mkdir(parents=True)
            (logbook / "benchmark-scorecard.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            document = _v2_index()
            document["children"] = [{"path": "runs/run-1", "status": "complete"}]
            _write_index(logbook, document)

            snapshot = read_logbook(logbook)

            self.assertEqual(snapshot.state, LogbookState.CURRENT_INDEXED)
            self.assertEqual(snapshot.run_kind, "real-benchmark")
            self.assertEqual(snapshot.status, "running")
            self.assertEqual(snapshot.stage, "preflight")
            self.assertEqual(snapshot.started_at, "2026-08-19T00:00:00Z")
            self.assertEqual(snapshot.updated_at, "2026-08-19T00:01:00Z")
            self.assertIsNone(snapshot.terminal_at)
            self.assertEqual(snapshot.regatta, "demo-regatta")
            self.assertEqual(snapshot.course, "demo-course")
            self.assertEqual(snapshot.comparisons[0].name, "demo-comparison")
            self.assertEqual(
                snapshot.comparisons[0].vessels,
                ("baseline", "challenger"),
            )
            artifact = snapshot.artifact("benchmark_scorecard")
            self.assertIsNotNone(artifact)
            assert artifact is not None
            self.assertEqual(
                artifact.path,
                (logbook / "benchmark-scorecard.json").resolve(),
            )
            self.assertFalse(artifact.recorded_present)
            self.assertTrue(artifact.present)
            self.assertEqual(
                snapshot.children[0].path,
                (logbook / "runs" / "run-1").resolve(),
            )
            self.assertTrue(snapshot.children[0].present)

    def test_current_index_remains_portable_when_logbook_moves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original = root / "original"
            original.mkdir()
            (original / "benchmark-scorecard.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            _write_index(original, _v2_index())
            moved = original.rename(root / "moved")

            snapshot = require_logbook(moved)

            artifact = snapshot.artifact("benchmark_scorecard")
            self.assertIsNotNone(artifact)
            assert artifact is not None
            self.assertEqual(
                artifact.path,
                (moved / "benchmark-scorecard.json").resolve(),
            )
            self.assertTrue(artifact.present)

    def test_current_index_rejects_escaping_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = root / "logbook"
            logbook.mkdir()
            (logbook / "benchmark-scorecard.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            for reference in ("../outside.json", str(root / "outside.json")):
                with self.subTest(reference=reference):
                    document = _v2_index()
                    document["artifacts"]["benchmark_scorecard"]["path"] = reference
                    _write_index(logbook, document)

                    snapshot = read_logbook(logbook)

                    self.assertEqual(snapshot.state, LogbookState.BROKEN)
                    self.assertIn("run index artifact", snapshot.error or "")

    def test_current_index_rejects_symlink_outside_logbook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = root / "logbook"
            outside = root / "outside"
            logbook.mkdir()
            outside.mkdir()
            (logbook / "escape").symlink_to(outside, target_is_directory=True)
            document = _v2_index()
            document["artifacts"]["benchmark_scorecard"]["path"] = (
                "escape/scorecard.json"
            )
            _write_index(logbook, document)

            snapshot = read_logbook(logbook)

            self.assertEqual(snapshot.state, LogbookState.BROKEN)
            self.assertIn("escapes the Logbook", snapshot.error or "")

    def test_historical_v1_references_follow_a_moved_logbook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original = root / "original"
            original.mkdir()
            scorecard = original / "benchmark-scorecard.json"
            scorecard.write_text("{}\n", encoding="utf-8")
            _write_index(original, _v1_index(original, scorecard))
            moved = original.rename(root / "moved")

            snapshot = require_logbook(moved)

            self.assertEqual(snapshot.state, LogbookState.HISTORICAL_V1)
            artifact = snapshot.artifact("benchmark_scorecard")
            self.assertIsNotNone(artifact)
            assert artifact is not None
            self.assertEqual(
                artifact.path,
                (moved / "benchmark-scorecard.json").resolve(),
            )
            self.assertTrue(artifact.present)

    def test_historical_v1_normalizes_windows_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = Path(temp_dir) / "logbook"
            logbook.mkdir()
            (logbook / "benchmark-scorecard.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            document = _v1_index(
                Path("C:/yacht/logbook"),
                Path("C:/yacht/logbook/benchmark-scorecard.json"),
            )
            document["logbook"] = r"C:\yacht\logbook"
            document["artifacts"]["benchmark_scorecard"]["path"] = (
                r"C:\yacht\logbook\benchmark-scorecard.json"
            )
            _write_index(logbook, document)

            snapshot = require_logbook(logbook)

            artifact = snapshot.artifact("benchmark_scorecard")
            self.assertIsNotNone(artifact)
            assert artifact is not None
            self.assertEqual(
                artifact.path,
                (logbook / "benchmark-scorecard.json").resolve(),
            )
            self.assertTrue(artifact.present)

    def test_historical_v1_rejects_outside_absolute_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = root / "logbook"
            logbook.mkdir()
            document = _v1_index(logbook, root / "outside.json")
            _write_index(logbook, document)

            snapshot = read_logbook(logbook)

            self.assertEqual(snapshot.state, LogbookState.BROKEN)
            self.assertIn("outside its Logbook", snapshot.error or "")

    def test_reads_scorecard_only_logbook_without_interpreting_scorecard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = Path(temp_dir) / "logbook"
            logbook.mkdir()
            (logbook / "benchmark-scorecard.json").write_text(
                "{not interpreted}\n",
                encoding="utf-8",
            )

            snapshot = require_logbook(logbook)

            self.assertEqual(snapshot.state, LogbookState.LEGACY_SCORECARD_ONLY)
            self.assertEqual(snapshot.run_kind, "real-benchmark")
            self.assertEqual(
                snapshot.artifact("benchmark_scorecard").path,
                (logbook / "benchmark-scorecard.json").resolve(),
            )

    def test_scorecard_only_logbook_rejects_outside_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = root / "logbook"
            logbook.mkdir()
            outside = root / "outside.json"
            outside.write_text("{}\n", encoding="utf-8")
            (logbook / "benchmark-scorecard.json").symlink_to(outside)

            snapshot = read_logbook(logbook)

            self.assertEqual(snapshot.state, LogbookState.BROKEN)
            self.assertIn("escapes the Logbook", snapshot.error or "")

    def test_malformed_present_index_never_falls_back_to_scorecard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = Path(temp_dir) / "logbook"
            logbook.mkdir()
            (logbook / RUN_INDEX_PATH).write_text("{not json", encoding="utf-8")
            (logbook / "benchmark-scorecard.json").write_text(
                "{}\n",
                encoding="utf-8",
            )

            snapshot = read_logbook(logbook)

            self.assertEqual(snapshot.state, LogbookState.BROKEN)
            self.assertIn("not valid JSON", snapshot.error or "")
            with self.assertRaisesRegex(ConfigError, "not valid JSON"):
                require_logbook(logbook)

    def test_undecodable_present_index_is_broken(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = Path(temp_dir) / "logbook"
            logbook.mkdir()
            (logbook / RUN_INDEX_PATH).write_bytes(b"\xff")
            (logbook / "benchmark-scorecard.json").write_text(
                "{}\n",
                encoding="utf-8",
            )

            snapshot = read_logbook(logbook)

            self.assertEqual(snapshot.state, LogbookState.BROKEN)
            self.assertIn("not valid JSON", snapshot.error or "")

    def test_dangling_present_index_symlink_is_broken(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = Path(temp_dir) / "logbook"
            logbook.mkdir()
            (logbook / RUN_INDEX_PATH).symlink_to(logbook / "missing-index.json")
            (logbook / "benchmark-scorecard.json").write_text(
                "{}\n",
                encoding="utf-8",
            )

            snapshot = read_logbook(logbook)

            self.assertEqual(snapshot.state, LogbookState.BROKEN)
            self.assertIn("run index artifact", snapshot.error or "")


def _v2_index() -> dict[str, object]:
    return {
        "schema": "yacht.run-index.v2",
        "run_kind": "real-benchmark",
        "status": "running",
        "stage": "preflight",
        "started_at": "2026-08-19T00:00:00Z",
        "updated_at": "2026-08-19T00:01:00Z",
        "config_path": "/tmp/regatta.toml",
        "regatta": "demo-regatta",
        "course": "demo-course",
        "comparisons": [
            {
                "name": "demo-comparison",
                "course": "demo-course",
                "vessels": ["baseline", "challenger"],
            }
        ],
        "artifacts": {
            "benchmark_scorecard": {
                "path": "benchmark-scorecard.json",
                "present": False,
            }
        },
    }


def _v1_index(logbook: Path, artifact: Path) -> dict[str, object]:
    return {
        "schema": "yacht.run-index.v1",
        "run_kind": "real-benchmark",
        "status": "complete",
        "updated_at": "2026-07-31T00:00:00Z",
        "config_path": "/tmp/regatta.toml",
        "logbook": str(logbook),
        "regatta": "demo-regatta",
        "course": "demo-course",
        "comparisons": [],
        "artifacts": {
            "benchmark_scorecard": {
                "path": str(artifact),
                "present": artifact.exists(),
            }
        },
    }


def _write_index(logbook: Path, document: dict[str, object]) -> None:
    logbook.mkdir(parents=True, exist_ok=True)
    (logbook / RUN_INDEX_PATH).write_text(
        json.dumps(document),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
