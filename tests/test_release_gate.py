import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_release_gate():
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "release_gate.py"
    spec = importlib.util.spec_from_file_location("yacht_release_gate", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gate = _load_release_gate()

COMPARISON = "skill-vs-baseline"
BASELINE_VESSEL = "claude-baseline"
CANDIDATE_VESSEL = "claude-with-skill"
TASK_ID = "convention-task"
AUTH_401_MESSAGE = (
    'is_error":true,"api_error_status":401,'
    '"result":"Invalid API key · Fix external API key"'
)


class ReleaseGateLiveAgentSuccessTests(unittest.TestCase):
    def test_401_failed_attempts_are_named_not_just_missing_repetition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_gate_surfaces(root, repetition=False)
            exception = {
                "type": "NonZeroAgentExitCodeError",
                "message": AUTH_401_MESSAGE,
            }
            _write_live_attempts(
                root,
                status="failed",
                tokens=0,
                exception=exception,
            )

            checks = _run_checks(root)
            full_ok, full_detail = _live_agent_check(checks, "full A/B")
            replay_ok, replay_detail = _live_agent_check(checks, "candidate replay")

            self.assertFalse(full_ok)
            self.assertFalse(replay_ok)
            self.assertIn("failed", full_detail)
            self.assertIn("NonZeroAgentExitCodeError", full_detail)
            self.assertIn(BASELINE_VESSEL, full_detail)
            self.assertIn(CANDIDATE_VESSEL, full_detail)
            self.assertIn("failed", replay_detail)
            self.assertIn("NonZeroAgentExitCodeError", replay_detail)
            self.assertIn(CANDIDATE_VESSEL, replay_detail)

    def test_successful_unresolved_attempts_pass_agent_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_gate_surfaces(root, repetition=True)
            _write_live_attempts(
                root,
                status="completed",
                tokens=0,
                exception=None,
                reward=0.0,
            )

            checks = _run_checks(root)
            full_ok, _ = _live_agent_check(checks, "full A/B")
            replay_ok, _ = _live_agent_check(checks, "candidate replay")

            self.assertTrue(full_ok)
            self.assertTrue(replay_ok)
            self.assertEqual([name for name, ok, _ in checks if not ok], [])

    def test_missing_expected_attempt_cannot_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_gate_surfaces(root, repetition=True)
            completed = _attempt(
                vessel=CANDIDATE_VESSEL,
                status="completed",
                tokens=0,
                exception=None,
                reward=0.0,
            )
            _write_attempt(root / "baseline", CANDIDATE_VESSEL, completed)
            _write_attempt(root / "candidate", CANDIDATE_VESSEL, completed)
            (root / "baseline" / "task-attempts" / COMPARISON / BASELINE_VESSEL).mkdir(
                parents=True
            )

            checks = _run_checks(root)
            full_ok, full_detail = _live_agent_check(checks, "full A/B")
            replay_ok, _ = _live_agent_check(checks, "candidate replay")

            self.assertFalse(full_ok)
            self.assertIn("missing", full_detail)
            self.assertIn(BASELINE_VESSEL, full_detail)
            self.assertTrue(replay_ok)

    def test_failed_attempt_cannot_pass_because_of_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_gate_surfaces(root, repetition=True)
            _write_live_attempts(
                root,
                status="failed",
                tokens=128,
                exception={
                    "type": "NonZeroAgentExitCodeError",
                    "message": "Command failed (exit 1): claude",
                },
                reward=0.0,
            )

            checks = _run_checks(root)
            full_ok, full_detail = _live_agent_check(checks, "full A/B")
            replay_ok, replay_detail = _live_agent_check(checks, "candidate replay")

            self.assertFalse(full_ok)
            self.assertFalse(replay_ok)
            self.assertIn(TASK_ID, full_detail)
            self.assertIn(TASK_ID, replay_detail)

    def test_unrelated_completed_attempt_cannot_replace_expected_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_gate_surfaces(root, repetition=True)
            for logbook_name, vessels in (
                ("baseline", (BASELINE_VESSEL, CANDIDATE_VESSEL)),
                ("candidate", (CANDIDATE_VESSEL,)),
            ):
                for vessel in vessels:
                    attempt = _attempt(
                        vessel=vessel,
                        status="completed",
                        tokens=0,
                        exception=None,
                        reward=0.0,
                    )
                    if logbook_name == "baseline" and vessel == BASELINE_VESSEL:
                        _write_attempt(
                            root / logbook_name,
                            vessel,
                            attempt,
                            filename="other.json",
                        )
                    else:
                        _write_attempt(root / logbook_name, vessel, attempt)

            checks = _run_checks(root)
            full_ok, full_detail = _live_agent_check(checks, "full A/B")
            replay_ok, _ = _live_agent_check(checks, "candidate replay")

            self.assertFalse(full_ok)
            self.assertIn("missing", full_detail)
            self.assertIn(BASELINE_VESSEL, full_detail)
            self.assertIn(TASK_ID, full_detail)
            self.assertTrue(replay_ok)


def _run_checks(root: Path) -> list[tuple[str, bool, str]]:
    return gate._checks(
        root / "baseline",
        root / "candidate",
        root / "export",
        root,
    )


def _live_agent_check(
    checks: list[tuple[str, bool, str]], run: str
) -> tuple[bool, str]:
    matches = [
        (ok, detail)
        for name, ok, detail in checks
        if "live agent" in name and run in name
    ]
    if not matches:
        raise AssertionError(
            f"missing live agent check for {run!r}: {[n for n, _, _ in checks]}"
        )
    return matches[0]


def _write_gate_surfaces(root: Path, *, repetition: bool) -> None:
    _write_json(
        root / "baseline" / "benchmark-scorecard.json",
        {
            "status": "complete",
            "comparisons": [
                {
                    "name": COMPARISON,
                    "vessels": [
                        {"name": BASELINE_VESSEL, "status": "measured"},
                        {"name": CANDIDATE_VESSEL, "status": "measured"},
                    ],
                }
            ],
        },
    )
    candidate_statistics = {
        "paired": {"grade": "insufficient-evidence"},
    }
    if repetition:
        candidate_statistics["repetition_guidance"] = {"plans": [{"repetitions": 2}]}
    _write_json(
        root / "candidate" / "benchmark-scorecard.json",
        {
            "status": "complete",
            "comparisons": [
                {
                    "name": COMPARISON,
                    "vessels": [
                        {
                            "name": BASELINE_VESSEL,
                            "status": "recorded",
                            "baseline_source": {"run_date": "2026-09-10T03:58:31Z"},
                        },
                        {"name": CANDIDATE_VESSEL, "status": "measured"},
                    ],
                    "statistics": candidate_statistics,
                }
            ],
        },
    )
    delivery = {
        "tool": "team-conventions",
        "status": "measured",
        "invoked_attempts": 0,
        "measured_attempts": 1,
    }
    _write_json(
        root / "baseline" / "task-attempt-scorecard.json",
        {
            "comparisons": [
                {
                    "name": COMPARISON,
                    "vessels": [
                        {"name": CANDIDATE_VESSEL, "tool_invocations": [delivery]}
                    ],
                }
            ]
        },
    )
    _write_json(root / "export" / "baseline.json", {"schema_version": "0.2.2"})
    _write_json(root / "export" / "candidate.json", {"schema_version": "0.2.2"})
    (root / "report.html").write_text(
        "recorded baseline from 2026-09-10\nSkill delivery\nTokens/res\n",
        encoding="utf-8",
    )


def _write_live_attempts(
    root: Path,
    *,
    status: str,
    tokens: int,
    exception: dict | None,
    reward: float = 0.0,
) -> None:
    for logbook_name, vessels in (
        ("baseline", (BASELINE_VESSEL, CANDIDATE_VESSEL)),
        ("candidate", (CANDIDATE_VESSEL,)),
    ):
        for vessel in vessels:
            _write_attempt(
                root / logbook_name,
                vessel,
                _attempt(
                    vessel=vessel,
                    status=status,
                    tokens=tokens,
                    exception=exception,
                    reward=reward,
                ),
            )


def _write_attempt(
    logbook: Path,
    vessel: str,
    attempt: dict,
    filename: str | None = None,
) -> None:
    _write_json(
        logbook
        / "task-attempts"
        / COMPARISON
        / vessel
        / (filename or f"{TASK_ID}.json"),
        attempt,
    )


def _attempt(
    *,
    vessel: str,
    status: str,
    tokens: int,
    exception: dict | None,
    reward: float,
) -> dict:
    evidence: dict = {"reward": reward}
    if exception is not None:
        evidence["exception"] = exception
    return {
        "status": status,
        "task": {"id": TASK_ID},
        "vessel": vessel,
        "agent": {"machine_evidence": evidence},
        "metrics": {"tokens": tokens, "duration_seconds": 1.0},
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
