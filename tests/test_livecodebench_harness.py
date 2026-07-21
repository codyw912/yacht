import json
import tempfile
import unittest
from pathlib import Path

from yacht.courses.livecodebench.harness import (
    evaluator_command,
    native_report_from_graded,
    run_livecodebench_evaluation,
)
from yacht.domain.model import ConfigError


def _write_inputs(root: Path, *, candidates: dict[str, str], window: list[str]):
    candidates_path = root / "candidate-patches.jsonl"
    candidates_path.write_text(
        "".join(
            json.dumps(
                {
                    "instance_id": question_id,
                    "model_name_or_path": "vessel-a",
                    "code": code,
                }
            )
            + "\n"
            for question_id, code in candidates.items()
        ),
        encoding="utf-8",
    )
    window_path = root / "lcb-window.json"
    window_path.write_text(json.dumps(window), encoding="utf-8")
    return candidates_path, window_path


def _write_eval_all(work_dir: Path, graded: dict[str, bool]) -> None:
    payload = [
        {"question_id": question_id, "graded_list": [passed], "pass@1": passed}
        for question_id, passed in graded.items()
    ]
    (work_dir / "custom-outputs_codegeneration_output_eval_all.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


class EvaluatorCommandTests(unittest.TestCase):
    def test_builds_containerized_evaluator_command(self) -> None:
        command = evaluator_command(
            Path("/work/custom-outputs.json"),
            work_dir=Path("/work"),
            release_version="release_v1",
            start_date="2023-05-01",
            end_date="2023-05-14",
        )

        self.assertEqual(command[:3], ["docker", "run", "--rm"])
        self.assertIn("/work:/work", command)
        self.assertIn("HF_HOME=/work/hf-cache", command)
        self.assertIn("yacht/lcb-runner:lcb-28fef95", command)
        self.assertIn("lcb_runner.runner.custom_evaluator", command)
        self.assertIn("--release_version", command)
        self.assertIn("release_v1", command)
        self.assertIn("--start_date", command)
        self.assertIn("--end_date", command)

    def test_omits_absent_window_bounds(self) -> None:
        command = evaluator_command(
            Path("/work/custom-outputs.json"),
            work_dir=Path("/work"),
            release_version="release_v1",
            start_date=None,
            end_date=None,
        )

        self.assertNotIn("--start_date", command)
        self.assertNotIn("--end_date", command)


class NativeReportTests(unittest.TestCase):
    def test_translates_graded_results_over_submitted_ids(self) -> None:
        report = native_report_from_graded(
            graded_by_question={"q1": True, "q2": False, "q3": False},
            submitted_ids=["q1", "q2"],
            window_ids=["q1", "q2", "q3"],
            release_version="release_v1",
            start_date="2023-05-01",
            end_date="2023-05-14",
        )

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["submitted_instances"], 2)
        self.assertEqual(report["resolved_ids"], ["q1"])
        self.assertEqual(report["unresolved_ids"], ["q2"])
        self.assertEqual(report["padding_instances"], 1)
        self.assertEqual(
            report["livecodebench"],
            {
                "release_version": "release_v1",
                "start_date": "2023-05-01",
                "end_date": "2023-05-14",
                "window_instances": 3,
            },
        )

    def test_rejects_missing_submitted_questions(self) -> None:
        with self.assertRaisesRegex(ConfigError, "missing submitted questions: q2"):
            native_report_from_graded(
                graded_by_question={"q1": True},
                submitted_ids=["q1", "q2"],
                window_ids=["q1", "q2"],
                release_version="release_v1",
                start_date=None,
                end_date=None,
            )


class RunEvaluationTests(unittest.TestCase):
    def test_pads_window_and_writes_native_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidates_path, window_path = _write_inputs(
                root,
                candidates={"q1": "print(1)"},
                window=["q1", "q2", "q3"],
            )
            work_dir = root / "work"
            commands = []

            def fake_runner(argv, cwd):
                commands.append(argv)
                _write_eval_all(work_dir, {"q1": True, "q2": False, "q3": False})
                return 0

            summary = run_livecodebench_evaluation(
                candidates_path=candidates_path,
                window_path=window_path,
                work_dir=work_dir,
                report_dir=root / "native-report",
                run_id="run-1",
                vessel_name="vessel-a",
                release_version="release_v1",
                start_date="2023-05-01",
                end_date="2023-05-14",
                command_runner=fake_runner,
            )

            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["submitted_instances"], 1)
            self.assertEqual(summary["resolved_instances"], 1)
            self.assertEqual(summary["padding_instances"], 2)
            outputs = json.loads(
                (work_dir / "custom-outputs.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                outputs,
                [
                    {"question_id": "q1", "code_list": ["print(1)"]},
                    {"question_id": "q2", "code_list": [""]},
                    {"question_id": "q3", "code_list": [""]},
                ],
            )
            report = json.loads(
                (root / "native-report/vessel-a.run-1.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["submitted_ids"], ["q1"])
            self.assertEqual(report["resolved_ids"], ["q1"])
            self.assertEqual(len(commands), 1)

    def test_rejects_candidates_outside_the_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidates_path, window_path = _write_inputs(
                root,
                candidates={"outside": "print(1)"},
                window=["q1"],
            )

            with self.assertRaisesRegex(ConfigError, "outside the window: outside"):
                run_livecodebench_evaluation(
                    candidates_path=candidates_path,
                    window_path=window_path,
                    work_dir=root / "work",
                    report_dir=root / "native-report",
                    run_id="run-1",
                    vessel_name="vessel-a",
                    release_version="release_v1",
                    start_date=None,
                    end_date=None,
                    command_runner=lambda argv, cwd: 0,
                )

    def test_fails_when_evaluator_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidates_path, window_path = _write_inputs(
                root,
                candidates={"q1": "print(1)"},
                window=["q1"],
            )

            with self.assertRaisesRegex(ConfigError, "exit code 2"):
                run_livecodebench_evaluation(
                    candidates_path=candidates_path,
                    window_path=window_path,
                    work_dir=root / "work",
                    report_dir=root / "native-report",
                    run_id="run-1",
                    vessel_name="vessel-a",
                    release_version="release_v1",
                    start_date=None,
                    end_date=None,
                    command_runner=lambda argv, cwd: 2,
                )


if __name__ == "__main__":
    unittest.main()
