import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from yacht.cli import main
from yacht.logbook.io import write_json
from yacht.reports.html_report import render_benchmark_html, render_smoke_html


def _scorecard(
    *,
    resolved_delta: int = 0,
    rate_delta: float = 0.0,
    submitted: int = 1,
    challenger: str = "pi-plus-tool",
) -> dict:
    def vessel(name: str, resolved: int) -> dict:
        return {
            "name": name,
            "preflight_status": "passed",
            "preflight_reason": "preflight-passed",
            "preflight_artifact_path": f"logbook/preflight/{name}.json",
            "status": "measured",
            "eligible_for_benchmark": True,
            "resolved_instances": resolved,
            "submitted_instances": submitted,
            "resolution_rate": resolved / submitted if submitted else 0.0,
            "resolved_ids": [f"task-{index}" for index in range(resolved)],
            "unresolved_ids": [f"task-{index}" for index in range(resolved, submitted)],
        }

    vessel_counts = {
        "total_vessels": 2,
        "eligible_vessels": 2,
        "blocked_vessels": 0,
        "measured_vessels": 2,
        "missing_result_vessels": 0,
    }
    return {
        "schema": "yacht.benchmark-scorecard.v1",
        "regatta": "tool-claim-check",
        "course": "swe-bench-lite",
        "adapter": {
            "kind": "swe-bench",
            "dataset": "princeton-nlp/SWE-bench_Lite",
            "split": "test",
        },
        "status": "complete",
        "summary": {"total_comparisons": 1, **vessel_counts},
        "comparisons": [
            {
                "name": "baseline-vs-tool",
                "course": "swe-bench-lite",
                "summary": dict(vessel_counts),
                "delta": {
                    "baseline_vessel": "pi-baseline",
                    "challenger_vessel": challenger,
                    "resolved_instances_delta": resolved_delta,
                    "resolution_rate_delta": rate_delta,
                },
                "vessels": [
                    vessel("pi-baseline", 1),
                    vessel(challenger, 1 + resolved_delta),
                ],
            }
        ],
        "next_steps": [],
    }


def _attempts() -> dict:
    return {
        "comparisons": [
            {
                "name": "baseline-vs-tool",
                "summary": {},
                "vessels": [
                    {
                        "name": "pi-baseline",
                        "total_tokens": 1000,
                        "total_cost": 0.01,
                        "total_duration_seconds": 60.0,
                        "tool_call_count": 2,
                        "tool_call_counts": {"bash": 2},
                    },
                    {
                        "name": "pi-plus-tool",
                        "total_tokens": 800,
                        "total_cost": 0.008,
                        "total_duration_seconds": 45.0,
                        "tool_call_count": 5,
                        "tool_call_counts": {"bash": 2, "newtool": 3},
                    },
                ],
            }
        ]
    }


class BenchmarkHtmlTests(unittest.TestCase):
    def test_tied_verdict_with_small_sample_badge(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(),
            task_attempt_scorecard=_attempts(),
            logbook_dir=Path("logbook"),
        )

        self.assertIn("tied with", html)
        self.assertIn("small sample", html)
        self.assertIn('class="verdict tied"', html)

    def test_improved_verdict_without_badge_on_larger_sample(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(resolved_delta=2, rate_delta=0.4, submitted=5),
            task_attempt_scorecard=None,
            logbook_dir=Path("logbook"),
        )

        self.assertIn('class="verdict improved"', html)
        self.assertIn("resolved 2 more", html)
        self.assertNotIn("small sample", html)

    def test_regressed_verdict(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(resolved_delta=-1, rate_delta=-0.2, submitted=5),
            task_attempt_scorecard=None,
            logbook_dir=Path("logbook"),
        )

        self.assertIn('class="verdict regressed"', html)
        self.assertIn("resolved 1 fewer", html)

    def test_tool_call_evidence_table_lists_challenger_tool(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(),
            task_attempt_scorecard=_attempts(),
            logbook_dir=Path("logbook"),
        )

        self.assertIn("newtool", html)
        self.assertIn("actually", html)

    def test_escapes_untrusted_names(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(challenger="pi-<script>alert(1)</script>"),
            task_attempt_scorecard=None,
            logbook_dir=Path("logbook"),
        )

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_contains_no_external_references(self) -> None:
        html = render_benchmark_html(
            scorecard=_scorecard(),
            task_attempt_scorecard=_attempts(),
            logbook_dir=Path("logbook"),
        )

        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)


class SmokeHtmlTests(unittest.TestCase):
    def test_renders_artifact_checklist(self) -> None:
        html = render_smoke_html(
            smoke_status={
                "status": "ready",
                "artifacts": [
                    {
                        "name": "run-index",
                        "path": "logbook/run-index.json",
                        "present": True,
                    },
                    {"name": "scorecard", "path": "logbook/x.json", "present": False},
                ],
                "next_step": "uv run yacht report --logbook logbook",
            },
            logbook_dir=Path("logbook"),
        )

        self.assertIn("Smoke status: ready", html)
        self.assertIn("present", html)
        self.assertIn("missing", html)
        self.assertIn("yacht report", html)


class HtmlReportCommandTests(unittest.TestCase):
    def test_report_html_writes_benchmark_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            output_path = Path(temp_dir) / "report.html"
            write_json(
                logbook_dir / "run-index.json",
                {"schema": "yacht.run-index.v1", "run_kind": "real-benchmark"},
            )
            write_json(logbook_dir / "benchmark-scorecard.json", _scorecard())

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "html",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            html = output_path.read_text(encoding="utf-8")
            self.assertTrue(html.startswith("<!doctype html>"))
            self.assertIn("tool-claim-check", html)

    def test_report_html_rejects_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir) / "logbook"
            write_json(
                logbook_dir / "run-index.json",
                {"schema": "yacht.run-index.v1", "run_kind": "real-benchmark"},
            )
            write_json(logbook_dir / "benchmark-scorecard.json", _scorecard())
            stderr = StringIO()

            from contextlib import redirect_stderr

            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(logbook_dir),
                        "--format",
                        "html",
                        "--vessel",
                        "pi-baseline",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("html report always includes", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
