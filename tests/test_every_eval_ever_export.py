import json
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

from yacht.cli import main
from yacht.domain.model import ConfigError
from yacht.reports.every_eval_ever import (
    build_every_eval_ever_export,
    write_every_eval_ever_export,
)


RETRIEVED = "1785270726.946333"
RUN_DATE = "2026-07-28T13:03:48.215730Z"
BASELINE_RUN_DATE = "2026-07-26T20:08:37.563525Z"


class EveryEvalEverExportTests(unittest.TestCase):
    def test_aggregate_document_carries_wilson_interval_and_pass_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = _logbook(Path(temp_dir))

            exports = build_every_eval_ever_export(
                logbook_dir=logbook,
                retrieved_timestamp=RETRIEVED,
            )

            challenger = _by_vessel(exports, "candidate")["document"]
            self.assertEqual(challenger["schema_version"], "0.2.2")
            self.assertEqual(challenger["eval_library"]["name"], "yacht")
            self.assertEqual(
                challenger["source_metadata"],
                {
                    "source_type": "evaluation_run",
                    "source_organization_name": "Acme",
                    "evaluator_relationship": "first_party",
                    "source_name": "skill-regatta",
                    "source_organization_url": "https://acme.example",
                },
            )
            result = challenger["evaluation_results"][0]
            self.assertEqual(result["metric_config"]["metric_id"], "pass_rate")
            self.assertEqual(result["metric_config"]["metric_kind"], "pass_rate")
            self.assertIs(result["metric_config"]["lower_is_better"], False)
            self.assertEqual(result["score_details"]["score"], 0.75)
            interval = result["score_details"]["uncertainty"]["confidence_interval"]
            self.assertEqual(interval["method"], "wilson")
            self.assertEqual(interval["confidence_level"], 0.95)
            self.assertLess(interval["lower"], 0.75)
            self.assertGreater(interval["upper"], 0.75)

    def test_comparison_travels_as_context_never_as_a_score(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = _logbook(Path(temp_dir))

            exports = build_every_eval_ever_export(
                logbook_dir=logbook,
                retrieved_timestamp=RETRIEVED,
            )

            challenger = _by_vessel(exports, "candidate")["document"]
            result = challenger["evaluation_results"][0]
            context = result["additional_details"]
            self.assertEqual(context["yacht_compared_against"], "control")
            self.assertEqual(context["yacht_resolved_delta"], "1")
            self.assertEqual(context["yacht_evidence_grade"], "insufficient-evidence")
            self.assertEqual(context["yacht_treatment_delivery"], "delivered")
            # Only the pass rate is a score; the delta is context.
            self.assertEqual(len(challenger["evaluation_results"]), 1)
            self.assertEqual(result["metric_config"]["metric_id"], "pass_rate")
            # additional_details values must all be strings per the schema.
            for value in context.values():
                self.assertIsInstance(value, str)

    def test_recorded_baseline_keeps_its_own_measurement_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = _logbook(Path(temp_dir), recorded_baseline=True)

            exports = build_every_eval_ever_export(
                logbook_dir=logbook,
                retrieved_timestamp=RETRIEVED,
            )

            baseline = _by_vessel(exports, "control")["document"]
            challenger = _by_vessel(exports, "candidate")["document"]
            self.assertEqual(baseline["evaluation_timestamp"], BASELINE_RUN_DATE)
            self.assertEqual(challenger["evaluation_timestamp"], RUN_DATE)
            context = baseline["evaluation_results"][0]["additional_details"]
            self.assertEqual(context["yacht_vessel_result"], "recorded-baseline")
            self.assertEqual(context["yacht_baseline_logbook"], "/tmp/recorded")

    def test_vessel_configuration_is_recorded_beside_the_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = _logbook(Path(temp_dir))

            exports = build_every_eval_ever_export(
                logbook_dir=logbook,
                retrieved_timestamp=RETRIEVED,
            )

            challenger = _by_vessel(exports, "candidate")["document"]
            model_info = challenger["model_info"]
            self.assertEqual(model_info["id"], "anthropic/claude-haiku-4-5")
            self.assertEqual(model_info["developer"], "anthropic")
            details = model_info["additional_details"]
            self.assertEqual(details["yacht_vessel"], "candidate")
            self.assertEqual(details["harness_version"], "2.1.215")
            self.assertEqual(details["skill_delivery"], "team-conventions: 2/2 invoked")
            # Two rows share a model id and differ only by configuration.
            baseline = _by_vessel(exports, "control")["document"]
            self.assertEqual(baseline["model_info"]["id"], model_info["id"])
            self.assertNotEqual(
                baseline["model_info"]["additional_details"]["yacht_vessel"],
                details["yacht_vessel"],
            )

    def test_instance_rows_are_agentic_transcripts_without_invented_counts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = _logbook(Path(temp_dir))

            exports = build_every_eval_ever_export(
                logbook_dir=logbook,
                retrieved_timestamp=RETRIEVED,
            )

            rows = _by_vessel(exports, "candidate")["rows"]
            self.assertEqual(len(rows), 4)
            row = next(row for row in rows if row["sample_id"] == "task-1")
            self.assertEqual(row["interaction_type"], "agentic")
            self.assertIsNone(row["output"])
            self.assertEqual(
                [turn["role"] for turn in row["messages"]], ["user", "assistant"]
            )
            self.assertEqual(row["evaluation"]["num_turns"], 2)
            self.assertEqual(row["input"]["reference"], [])
            self.assertTrue(row["evaluation"]["is_correct"])
            # tool_calls_count would misreport distinct tools as calls.
            self.assertNotIn("tool_calls_count", row["evaluation"])
            self.assertEqual(row["metadata"]["observed_tools"], "Bash, Skill:x")

    def test_export_refuses_without_declared_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = _logbook(Path(temp_dir), attribution=False)

            with self.assertRaises(ConfigError) as raised:
                build_every_eval_ever_export(
                    logbook_dir=logbook,
                    retrieved_timestamp=RETRIEVED,
                )

            message = str(raised.exception)
            self.assertIn("[export]", message)
            self.assertIn("evaluator_relationship", message)

    def test_export_refuses_when_model_provenance_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = _logbook(Path(temp_dir), provenance=False)

            with self.assertRaises(ConfigError) as raised:
                build_every_eval_ever_export(
                    logbook_dir=logbook,
                    retrieved_timestamp=RETRIEVED,
                )

            self.assertIn("cannot determine the model", str(raised.exception))

    def test_write_export_pairs_aggregate_and_instance_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _logbook(root)
            output_dir = root / "export"

            manifest = write_every_eval_ever_export(
                logbook_dir=logbook,
                output_dir=output_dir,
                retrieved_timestamp=RETRIEVED,
            )

            self.assertEqual(len(manifest["exports"]), 2)
            for export in manifest["exports"]:
                aggregate = json.loads(
                    Path(export["aggregate_path"]).read_text(encoding="utf-8")
                )
                instance_path = Path(export["instance_path"])
                detailed = aggregate["detailed_evaluation_results"]
                self.assertEqual(detailed["file_path"], instance_path.name)
                self.assertEqual(detailed["format"], "jsonl")
                rows = [
                    json.loads(line)
                    for line in instance_path.read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual(detailed["total_rows"], len(rows))
                self.assertTrue(
                    all(
                        row["evaluation_id"] == aggregate["evaluation_id"]
                        for row in rows
                    )
                )

    def test_cli_requires_an_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = _logbook(Path(temp_dir))
            stderr = StringIO()

            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "report",
                        "--logbook",
                        str(logbook),
                        "--format",
                        "every-eval-ever",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("--output <directory>", stderr.getvalue())


def _by_vessel(exports: list[dict], vessel: str) -> dict:
    return next(export for export in exports if export["vessel"] == vessel)


def _logbook(
    root: Path,
    *,
    recorded_baseline: bool = False,
    attribution: bool = True,
    provenance: bool = True,
) -> Path:
    logbook = root / "logbook"
    logbook.mkdir(parents=True, exist_ok=True)
    handoff = {
        "schema": "yacht.course-handoff.v1",
        "regatta": "skill-regatta",
        "course": "team-conventions-ab",
        "status": "planned",
        "adapter": {
            "kind": "custom-eval",
            "dataset": "/repo/examples/custom-evals",
            "split": "v1",
            "harness": "harbor",
            "content_digest": "sha256:abc123",
        },
        "tasks": [
            {"id": f"task-{index}", "title": f"Task {index}", "difficulty": 1}
            for index in range(1, 5)
        ],
        "comparisons": [
            {
                "name": "skill-vs-baseline",
                "course": "team-conventions-ab",
                "vessels": ["control", "candidate"],
            }
        ],
        "expected_outputs": {
            "candidate_patches": "course-handoff/custom-eval/candidate-patches.jsonl",
            "grading_report": "course-handoff/custom-eval/grading-report.json",
        },
        "grading": {
            "delegated_to": "custom-eval",
            "execution": "harbor-harness",
            "status": "planned",
        },
    }
    if attribution:
        handoff["export"] = {
            "source_organization_name": "Acme",
            "evaluator_relationship": "first_party",
            "source_organization_url": "https://acme.example",
        }
    _write(logbook / "course-handoff.json", handoff)

    control = _vessel_score("control", resolved=["task-1", "task-2"])
    if recorded_baseline:
        control["status"] = "recorded"
        for key in (
            "eligible_for_benchmark",
            "preflight_status",
            "preflight_reason",
            "preflight_artifact_path",
        ):
            control.pop(key)
        control["baseline_source"] = {
            "logbook": "/tmp/recorded",
            "vessel": "control",
            "run_date": BASELINE_RUN_DATE,
            "provenance": _provenance(),
        }
    candidate = _vessel_score(
        "candidate",
        resolved=["task-1", "task-2", "task-3"],
    )
    _write(
        logbook / "benchmark-scorecard.json",
        {
            "schema": "yacht.benchmark-scorecard.v1",
            "regatta": "skill-regatta",
            "course": "team-conventions-ab",
            "adapter": {
                "kind": "custom-eval",
                "dataset": "/repo/examples/custom-evals",
                "split": "v1",
            },
            "status": "complete",
            "summary": {},
            "comparisons": [
                {
                    "name": "skill-vs-baseline",
                    "course": "team-conventions-ab",
                    "summary": {},
                    "delta": {
                        "baseline_vessel": "control",
                        "challenger_vessel": "candidate",
                        "resolved_instances_delta": 1,
                        "resolution_rate_delta": 0.25,
                    },
                    "statistics": {
                        "confidence_level": 0.95,
                        "paired": {
                            "grade": "insufficient-evidence",
                            "p_value": 1.0,
                            "discordant_baseline_only": 0,
                            "discordant_challenger_only": 1,
                        },
                    },
                    "delivery": {
                        "vessel": "candidate",
                        "status": "delivered",
                        "tools": [],
                    },
                    "vessels": [control, candidate],
                }
            ],
        },
    )

    vessels = []
    for name in ("control", "candidate"):
        entry: dict = {
            "name": name,
            "status": "measured",
            "task_attempts": 4,
            "completed_attempts": 4,
            "failed_attempts": 0,
            "success_rate": 1.0,
            "tool_call_count": 2,
            "total_tokens": 1000,
            "total_duration_seconds": 30.0,
            "artifact_paths": [],
        }
        if provenance:
            entry["provenance"] = _provenance()
        if name == "candidate":
            entry["tool_invocations"] = [
                {
                    "tool": "team-conventions",
                    "kind": "agent-skill",
                    "expected_calls": ["Skill:x"],
                    "status": "measured",
                    "attempts": 2,
                    "measured_attempts": 2,
                    "invoked_attempts": 2,
                }
            ]
        vessels.append(entry)
    _write(
        logbook / "task-attempt-scorecard.json",
        {
            "schema": "yacht.task-attempt-scorecard.v1",
            "regatta": "skill-regatta",
            "course": "team-conventions-ab",
            "status": "complete",
            "summary": {},
            "comparisons": [{"name": "skill-vs-baseline", "vessels": vessels}],
        },
    )
    _write(
        logbook / "run-index.json",
        {
            "schema": "yacht.run-index.v1",
            "run_kind": "real-benchmark",
            "status": "complete",
            "updated_at": RUN_DATE,
        },
    )
    attempts_dir = logbook / "task-attempts" / "skill-vs-baseline" / "candidate"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    _write(
        attempts_dir / "task-1.json",
        {
            "prompt": "Add a tool module following team conventions",
            "task": {"id": "task-1", "title": "Task 1"},
            "agent": {
                "response": "done",
                "tool_calls": ["Bash", "Skill:x"],
                "machine_evidence": {"usage": {"input_tokens": 10, "output_tokens": 5}},
            },
        },
    )
    return logbook


def _vessel_score(name: str, *, resolved: list[str]) -> dict:
    unresolved = [
        f"task-{index}" for index in range(1, 5) if f"task-{index}" not in resolved
    ]
    return {
        "name": name,
        "status": "measured",
        "submitted_instances": 4,
        "resolved_instances": len(resolved),
        "resolution_rate": len(resolved) / 4,
        "resolved_ids": resolved,
        "unresolved_ids": unresolved,
        "eligible_for_benchmark": True,
        "preflight_status": "passed",
        "preflight_reason": "preflight-passed",
        "preflight_artifact_path": "preflight/x.json",
    }


def _provenance() -> dict:
    return {
        "yacht": {"version": "0.7.0"},
        "harness": {"name": "claude-code", "version": "2.1.215"},
        "model": {
            "configured": "anthropic/claude-haiku-4-5",
            "resolved": "claude-haiku-4-5",
        },
        "runtime": {"backend": "harbor", "image": "yacht/harbor-launcher:0.20.0"},
        "tools": [{"name": "team-conventions-skill", "version": None}],
    }


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
