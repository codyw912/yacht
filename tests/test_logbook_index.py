import json
import tempfile
import unittest
from pathlib import Path

from yacht.logbook.index import RUN_INDEX_PATH, write_run_index


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


if __name__ == "__main__":
    unittest.main()
