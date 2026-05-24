import json
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.preflight_artifacts import write_preflight_artifact
from yacht.cli import main
from yacht.courses.handoff import write_course_handoff
from yacht.reports.preflight_evidence import render_preflight_evidence_report
from yacht.reports.preflight_evidence import write_preflight_evidence_report


class PreflightEvidenceReportTests(unittest.TestCase):
    def test_report_summarizes_preflight_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_logbook(Path(temp_dir))
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-baseline",
                status="passed",
            )
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-plus-fff",
                status="failed",
            )

            report = write_preflight_evidence_report(logbook_dir)

            self.assertEqual(report["schema"], "yacht.preflight-evidence-report.v1")
            self.assertEqual(report["status"], "blocked")
            vessels = report["comparisons"][0]["vessels"]
            self.assertEqual(vessels[0]["name"], "pi-baseline")
            self.assertEqual(vessels[0]["status"], "eligible")
            self.assertTrue(vessels[0]["eligible_for_benchmark"])
            self.assertEqual(vessels[0]["reason"], "preflight-passed")
            self.assertEqual(vessels[1]["name"], "pi-plus-fff")
            self.assertEqual(vessels[1]["status"], "preflight-failed")
            self.assertFalse(vessels[1]["eligible_for_benchmark"])
            self.assertEqual(vessels[1]["reason"], "preflight-failed")
            saved = json.loads(
                (logbook_dir / "preflight-evidence-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(saved, report)

    def test_report_records_invalid_preflight_artifact_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_logbook(Path(temp_dir))
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-baseline",
                status="passed",
            )
            artifact_path = logbook_dir / "preflight/pi-vs-pi-fff/pi-baseline.json"
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact["vessel"] = "wrong-vessel"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

            report = write_preflight_evidence_report(logbook_dir)

            vessel = report["comparisons"][0]["vessels"][0]
            self.assertEqual(vessel["status"], "preflight-invalid")
            self.assertFalse(vessel["eligible_for_benchmark"])
            self.assertEqual(vessel["reason"], "preflight-invalid")
            self.assertIn("wrong-vessel", vessel["error"])

    def test_report_surfaces_unsupported_rigging_capability_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_logbook(Path(temp_dir))
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-baseline",
                status="passed",
            )
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-plus-fff",
                status="failed",
            )
            artifact_path = logbook_dir / "preflight/pi-vs-pi-fff/pi-plus-fff.json"
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact["checks"] = [
                {
                    "name": "rigging-capability-pi-fff-package",
                    "kind": "runtime-capability",
                    "origin": "rigging",
                    "origin_name": "pi-fff",
                    "required": True,
                    "status": "failed",
                    "evidence": {
                        "reason": (
                            "runtime backend host-nix does not support rigging "
                            "install method package yet"
                        )
                    },
                }
            ]
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

            report = write_preflight_evidence_report(logbook_dir)

            vessel = report["comparisons"][0]["vessels"][1]
            self.assertEqual(vessel["status"], "unsupported-rigging-capability")
            self.assertEqual(vessel["reason"], "unsupported-rigging-capability")
            self.assertFalse(vessel["eligible_for_benchmark"])

    def test_preflight_report_command_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_logbook(Path(temp_dir))
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-baseline",
                status="passed",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["preflight-report", "--logbook", str(logbook_dir)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema"], "yacht.preflight-evidence-report.v1")
            self.assertEqual(payload["status"], "blocked")

    def test_render_preflight_report_as_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = _prepared_logbook(Path(temp_dir))
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-baseline",
                status="passed",
            )
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-plus-fff",
                status="failed",
            )

            report = write_preflight_evidence_report(logbook_dir)

            rendered = render_preflight_evidence_report(report, "text")
            self.assertIn(
                "Preflight report: pi-fff-comparison / swe-bench-lite",
                rendered,
            )
            self.assertIn("Status: blocked", rendered)
            self.assertIn(
                "Summary: eligible=1 | blocked=1 | missing=0 | invalid=0 | total=2",
                rendered,
            )
            self.assertIn(
                (
                    "pi-vs-pi-fff | pi-plus-fff | preflight-failed | no | "
                    "preflight-failed | failed | "
                ),
                rendered,
            )

    def test_preflight_report_command_writes_markdown_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook_dir = _prepared_logbook(root)
            output_path = root / "preflight-report.md"
            write_preflight_artifact(
                logbook_dir=logbook_dir,
                comparison_name="pi-vs-pi-fff",
                vessel_name="pi-baseline",
                status="passed",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "preflight-report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "markdown",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            rendered = output_path.read_text(encoding="utf-8")
            self.assertIn("## Preflight report", rendered)
            self.assertIn("| Comparison | Vessel | Status | Eligible |", rendered)
            self.assertIn("| pi-vs-pi-fff | pi-baseline | eligible | yes |", rendered)

    def test_preflight_report_command_reports_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "preflight-report",
                        "--logbook",
                        str(Path(temp_dir) / "logbook"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "error: invalid regatta config: course handoff artifact not found",
                stderr.getvalue(),
            )
            self.assertNotIn("Traceback", stderr.getvalue())


def _prepared_logbook(root: Path) -> Path:
    logbook_dir = root / "logbook"
    write_course_handoff(Path("examples/pi-fff-provisioning.toml"), logbook_dir)
    return logbook_dir


if __name__ == "__main__":
    unittest.main()
