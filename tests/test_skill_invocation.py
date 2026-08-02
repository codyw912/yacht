import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from yacht.config.loader import load_regatta
from yacht.contracts.schemas import validate_task_attempt_document
from yacht.courses.terminal_bench.attempts_from_trials import (
    _observed_tool_calls,
    _tool_expectations,
)
from yacht.harnesses.claude_code import tool_calls_from_session_transcript
from yacht.reports.benchmark_scorecard import _delivery_block
from yacht.reports.task_attempt_scorecard import write_task_attempt_scorecard


EXAMPLE_CONFIG = Path("examples/custom-eval-skill-ab-smoke.toml")
MCP_EXAMPLE_CONFIG = Path("examples/container-claude-code-mcp-real-task-smoke.toml")
PI_MCP_EXAMPLE_CONFIG = Path("examples/custom-eval-pi-mcp-ab-smoke.toml")

SESSION_EVENTS = [
    {"type": "user", "message": {"content": "do the task"}},
    {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Skill",
                    "input": {"skill": "team-conventions"},
                },
                {"type": "tool_use", "name": "Write", "input": {"file_path": "x"}},
            ]
        },
    },
]


class SessionTranscriptTests(unittest.TestCase):
    def test_skill_invocations_are_qualified_by_skill_name(self) -> None:
        text = _jsonl(SESSION_EVENTS)

        self.assertEqual(
            tool_calls_from_session_transcript(text),
            ("Skill:team-conventions", "Write"),
        )

    def test_unrecognized_transcript_degrades_to_unmeasured(self) -> None:
        self.assertIsNone(tool_calls_from_session_transcript("not json at all"))
        self.assertIsNone(tool_calls_from_session_transcript(""))
        self.assertIsNone(
            tool_calls_from_session_transcript('{"no_type_field": true}\n')
        )

    def test_recognized_transcript_with_no_tools_is_measured_empty(self) -> None:
        text = _jsonl([{"type": "user", "message": {"content": "hi"}}])

        self.assertEqual(tool_calls_from_session_transcript(text), ())


class ObservedToolCallsTests(unittest.TestCase):
    def test_session_transcripts_measure_tool_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir)
            sessions = trial_dir / "agent" / "sessions" / "projects" / "-app"
            sessions.mkdir(parents=True)
            (sessions / "session.jsonl").write_text(
                _jsonl(SESSION_EVENTS),
                encoding="utf-8",
            )

            calls, source = _observed_tool_calls(trial_dir)

            self.assertEqual(calls, ["Skill:team-conventions", "Write"])
            self.assertEqual(source, "claude-code-session-transcript")

    def test_harness_evidence_measures_tool_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir)
            agent_dir = trial_dir / "agent"
            agent_dir.mkdir(parents=True)
            (agent_dir / "harness-evidence.json").write_text(
                json.dumps(
                    {
                        "schema": "yacht.harness-evidence.v1",
                        "response": "done",
                        "usage": {"input_tokens": 10, "output_tokens": 5},
                        "tool_calls": [{"name": "yach-search", "count": 3}],
                    }
                ),
                encoding="utf-8",
            )

            calls, source = _observed_tool_calls(trial_dir)

            self.assertEqual(calls, ["yach-search"])
            self.assertEqual(source, "harness-evidence")

    def test_missing_evidence_is_unmeasured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            calls, source = _observed_tool_calls(Path(temp_dir))

            self.assertEqual(calls, [])
            self.assertIsNone(source)

    def test_harness_evidence_without_tool_calls_is_unmeasured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir)
            agent_dir = trial_dir / "agent"
            agent_dir.mkdir(parents=True)
            (agent_dir / "harness-evidence.json").write_text(
                json.dumps(
                    {
                        "schema": "yacht.harness-evidence.v1",
                        "response": "done",
                        "usage": {"input_tokens": 10, "output_tokens": 5},
                    }
                ),
                encoding="utf-8",
            )

            calls, source = _observed_tool_calls(trial_dir)

            self.assertEqual(calls, [])
            self.assertIsNone(source)


class ToolExpectationTests(unittest.TestCase):
    def test_skill_expectation_uses_frontmatter_name(self) -> None:
        regatta = load_regatta(EXAMPLE_CONFIG)
        vessel = next(
            vessel for vessel in regatta.vessels if vessel.name == "claude-with-skill"
        )
        runtime = regatta.runtime_recipes[vessel.runtime]

        expectations = _tool_expectations(regatta, vessel, runtime)

        self.assertEqual(
            expectations,
            [
                {
                    "tool": "team-conventions",
                    "kind": "agent-skill",
                    "expected_calls": ["Skill:team-conventions"],
                }
            ],
        )

    def test_baseline_vessel_has_no_expectations(self) -> None:
        regatta = load_regatta(EXAMPLE_CONFIG)
        vessel = next(
            vessel for vessel in regatta.vessels if vessel.name == "claude-baseline"
        )
        runtime = regatta.runtime_recipes[vessel.runtime]

        self.assertEqual(_tool_expectations(regatta, vessel, runtime), [])

    def test_mcp_expectation_derives_namespace_from_install_step(self) -> None:
        regatta = load_regatta(MCP_EXAMPLE_CONFIG)
        vessel = next(
            vessel
            for vessel in regatta.vessels
            if vessel.name == "claude-code-container-fff-mcp"
        )
        runtime = regatta.runtime_recipes[vessel.runtime]

        expectations = _tool_expectations(regatta, vessel, runtime)

        self.assertEqual(
            expectations,
            [
                {
                    "tool": "fff",
                    "kind": "mcp-server",
                    "expected_calls": ["mcp__fff__"],
                }
            ],
        )

    def test_mcp_expectation_omitted_for_unnamespaced_harness(self) -> None:
        regatta = load_regatta(MCP_EXAMPLE_CONFIG)
        vessel = next(
            vessel
            for vessel in regatta.vessels
            if vessel.name == "claude-code-container-fff-mcp"
        )
        runtime = replace(regatta.runtime_recipes[vessel.runtime], harness="pi")

        self.assertEqual(_tool_expectations(regatta, vessel, runtime), [])


class PiProviderExpectationTests(unittest.TestCase):
    def test_provider_guarantee_emits_the_namespace_expectation(self) -> None:
        regatta = load_regatta(PI_MCP_EXAMPLE_CONFIG)
        vessel = next(v for v in regatta.vessels if v.name == "pi-with-mcp")
        runtime = regatta.runtime_recipes[vessel.runtime]

        expectations = _tool_expectations(regatta, vessel, runtime)

        mcp = [e for e in expectations if e["kind"] == "mcp-server"]
        self.assertEqual(
            mcp,
            [
                {
                    "tool": "files",
                    "kind": "mcp-server",
                    "expected_calls": ["mcp__files_"],
                }
            ],
        )

    def test_stock_pi_vessel_gets_no_mcp_expectation(self) -> None:
        regatta = load_regatta(PI_MCP_EXAMPLE_CONFIG)
        vessel = next(v for v in regatta.vessels if v.name == "pi-baseline")
        runtime = regatta.runtime_recipes[vessel.runtime]

        self.assertEqual(_tool_expectations(regatta, vessel, runtime), [])


class DeliveryMetricsTests(unittest.TestCase):
    def test_scorecard_reports_delivery_rates_over_measured_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir)
            _write_attempt(
                logbook_dir,
                task_id="task-1",
                status="completed",
                tool_calls=["Skill:team-conventions", "Write"],
                measured=True,
            )
            _write_attempt(
                logbook_dir,
                task_id="task-2",
                status="failed",
                tool_calls=[],
                measured=True,
            )
            _write_attempt(
                logbook_dir,
                task_id="task-3",
                status="completed",
                tool_calls=[],
                measured=False,
            )

            scorecard = write_task_attempt_scorecard(logbook_dir)

            vessel = scorecard["comparisons"][0]["vessels"][0]
            (invocation,) = vessel["tool_invocations"]
            self.assertEqual(invocation["status"], "measured")
            self.assertEqual(invocation["attempts"], 3)
            self.assertEqual(invocation["measured_attempts"], 2)
            self.assertEqual(invocation["invoked_attempts"], 1)
            self.assertEqual(invocation["invocation_rate"], 0.5)
            self.assertEqual(invocation["completed_attempts"], 1)
            self.assertEqual(invocation["invoked_completed_attempts"], 1)
            self.assertEqual(invocation["completed_invocation_rate"], 1.0)

    def test_mcp_delivery_matches_delimited_namespace(self) -> None:
        mcp_expectation = [
            {
                "tool": "fff",
                "kind": "mcp-server",
                "expected_calls": ["mcp__fff__"],
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir)
            _write_attempt(
                logbook_dir,
                task_id="task-1",
                status="completed",
                tool_calls=["mcp__fff__fffind", "mcp__fff__ffgrep", "Write"],
                measured=True,
                expectations=mcp_expectation,
            )
            _write_attempt(
                logbook_dir,
                task_id="task-2",
                status="completed",
                tool_calls=["mcp__fff2__search"],
                measured=True,
                expectations=mcp_expectation,
            )

            scorecard = write_task_attempt_scorecard(logbook_dir)

            vessel = scorecard["comparisons"][0]["vessels"][0]
            (invocation,) = vessel["tool_invocations"]
            self.assertEqual(invocation["kind"], "mcp-server")
            self.assertEqual(invocation["measured_attempts"], 2)
            self.assertEqual(invocation["invoked_attempts"], 1)
            self.assertEqual(invocation["observed_tools"], ["fffind", "ffgrep"])

    def test_scorecard_reports_unmeasured_when_no_attempt_has_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook_dir = Path(temp_dir)
            _write_attempt(
                logbook_dir,
                task_id="task-1",
                status="completed",
                tool_calls=[],
                measured=False,
            )

            scorecard = write_task_attempt_scorecard(logbook_dir)

            vessel = scorecard["comparisons"][0]["vessels"][0]
            (invocation,) = vessel["tool_invocations"]
            self.assertEqual(invocation["status"], "unmeasured")
            self.assertNotIn("invocation_rate", invocation)


class DeliveryBlockTests(unittest.TestCase):
    def test_measured_zero_invocations_is_not_delivered(self) -> None:
        delivery = _delivery_block(
            "skill-vs-baseline",
            [{"name": "control"}, {"name": "candidate"}],
            {
                ("skill-vs-baseline", "candidate"): [
                    _invocation_entry(invoked_attempts=0)
                ],
            },
        )

        assert delivery is not None
        self.assertEqual(delivery["status"], "not-delivered")

    def test_invoked_treatment_is_delivered(self) -> None:
        delivery = _delivery_block(
            "skill-vs-baseline",
            [{"name": "control"}, {"name": "candidate"}],
            {
                ("skill-vs-baseline", "candidate"): [
                    _invocation_entry(invoked_attempts=3)
                ],
            },
        )

        assert delivery is not None
        self.assertEqual(delivery["status"], "delivered")
        self.assertEqual(delivery["vessel"], "candidate")

    def test_unmeasured_treatment_is_labeled_unmeasured(self) -> None:
        delivery = _delivery_block(
            "skill-vs-baseline",
            [{"name": "control"}, {"name": "candidate"}],
            {
                ("skill-vs-baseline", "candidate"): [
                    {
                        "tool": "team-conventions",
                        "kind": "agent-skill",
                        "expected_calls": ["Skill:team-conventions"],
                        "status": "unmeasured",
                        "attempts": 3,
                        "measured_attempts": 0,
                    }
                ],
            },
        )

        assert delivery is not None
        self.assertEqual(delivery["status"], "unmeasured")

    def test_shared_tools_are_not_treatment(self) -> None:
        entry = _invocation_entry(invoked_attempts=3)
        self.assertIsNone(
            _delivery_block(
                "skill-vs-baseline",
                [{"name": "control"}, {"name": "candidate"}],
                {
                    ("skill-vs-baseline", "control"): [entry],
                    ("skill-vs-baseline", "candidate"): [entry],
                },
            )
        )


class AggregateInvocationTests(unittest.TestCase):
    def test_aggregate_unions_observed_mcp_tools_across_runs(self) -> None:
        from yacht.reports.benchmark_aggregate import (
            _accumulate_tool_invocations,
            _finalized_tool_invocations,
        )

        totals: dict[str, dict[str, object]] = {}
        _accumulate_tool_invocations(totals, [_mcp_run_entry(["fffind"])])
        _accumulate_tool_invocations(totals, [_mcp_run_entry(["ffgrep"])])

        (entry,) = _finalized_tool_invocations(totals)

        self.assertEqual(entry["observed_tools"], ["fffind", "ffgrep"])
        self.assertEqual(entry["invoked_attempts"], 2)


class DeliveryTableTests(unittest.TestCase):
    def test_html_delivery_table_lists_observed_mcp_tools(self) -> None:
        from yacht.reports.html_report import _delivery_table

        table = _delivery_table(
            {
                "vessels": [
                    {
                        "name": "candidate",
                        "tool_invocations": [_mcp_run_entry(["fffind", "ffgrep"])],
                    }
                ]
            }
        )

        self.assertIn("observed: fffind, ffgrep", table)


def _mcp_run_entry(observed_tools: list[str]) -> dict[str, object]:
    return {
        "tool": "fff",
        "kind": "mcp-server",
        "expected_calls": ["mcp__fff__"],
        "status": "measured",
        "attempts": 1,
        "measured_attempts": 1,
        "invoked_attempts": 1,
        "invocation_rate": 1.0,
        "invocation_interval": {"low": 0.2, "high": 1.0},
        "completed_attempts": 1,
        "invoked_completed_attempts": 1,
        "completed_invocation_rate": 1.0,
        "completed_invocation_interval": {"low": 0.2, "high": 1.0},
        "observed_tools": observed_tools,
    }


def _invocation_entry(*, invoked_attempts: int) -> dict[str, object]:
    return {
        "tool": "team-conventions",
        "kind": "agent-skill",
        "expected_calls": ["Skill:team-conventions"],
        "status": "measured",
        "attempts": 3,
        "measured_attempts": 3,
        "invoked_attempts": invoked_attempts,
        "invocation_rate": invoked_attempts / 3,
        "invocation_interval": {"low": 0.0, "high": 1.0},
    }


def _jsonl(events: list[dict[str, object]]) -> str:
    return "".join(json.dumps(event) + "\n" for event in events)


def _write_attempt(
    logbook_dir: Path,
    *,
    task_id: str,
    status: str,
    tool_calls: list[str],
    measured: bool,
    expectations: list[dict[str, object]] | None = None,
) -> None:
    agent: dict[str, object] = {
        "exit_code": 0 if status == "completed" else 1,
        "response": "",
        "tool_calls": tool_calls,
        "transcript_path": "/tmp/trial",
    }
    if measured:
        agent["tool_call_evidence"] = "claude-code-session-transcript"
    attempt = {
        "schema": "yacht.task-attempt.v1",
        "regatta": "skill-ab",
        "course": "team-conventions-ab",
        "comparison": "skill-vs-baseline",
        "vessel": "candidate",
        "model": "anthropic/claude-haiku-4-5",
        "rigging": ["team-conventions-skill"],
        "runtime": "harbor-claude",
        "status": status,
        "task": {"id": task_id, "title": "Task", "difficulty": 1},
        "runtime_context": {
            "backend": "harbor",
            "harness": "claude-code",
            "temp_home": "/tmp/trial",
            "workspace_path": "/tmp/trial",
            "command_prefix": [],
            "command": ["harbor", "run"],
            "cleanup_paths": [],
        },
        "prompt": "native",
        "agent": agent,
        "metrics": {"tokens": 100, "duration_seconds": 1.0},
        "secret_refs": [],
        "tool_expectations": expectations
        if expectations is not None
        else [
            {
                "tool": "team-conventions",
                "kind": "agent-skill",
                "expected_calls": ["Skill:team-conventions"],
            }
        ],
    }
    validate_task_attempt_document(attempt)
    path = logbook_dir / "task-attempts" / "skill-vs-baseline" / "candidate"
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{task_id}.json").write_text(
        json.dumps(attempt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
