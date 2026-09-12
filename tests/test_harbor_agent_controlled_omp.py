import asyncio
import contextlib
import hashlib
import importlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

LAUNCHER_ROOT = Path(__file__).resolve().parent.parent / "containers/harbor-launcher"
if str(LAUNCHER_ROOT) not in sys.path:
    sys.path.insert(0, str(LAUNCHER_ROOT))

controlled_omp = importlib.import_module("yacht_harbor_agents.controlled_omp")
captures = importlib.import_module("yacht_harbor_agents.captures")
quiesce = importlib.import_module("yacht_harbor_agents.quiesce")


FUTURE_Q = "FUTURE_MARKER_Q_UNIQUE"
FUTURE_X1 = "FUTURE_MARKER_X1_UNIQUE"
SECRET_VALUE = "sk-secret-yacht-test-value"
INITIAL = "write plans/retention-answers.json then wait"


def _retained_plan() -> dict:
    return {
        "mode": "retained",
        "max_turns": 2,
        "message_timeout_seconds": 600,
        "timeout_seconds": 7200,
        "initial_turn_id": "initial",
        "turns": [
            {"id": "Q", "instruction": FUTURE_Q},
            {"id": "X1", "instruction": FUTURE_X1},
        ],
        "captures": [
            {
                "id": "Q-0",
                "after": "Q",
                "path": "plans/retention-answers.json",
                "max_bytes": 1048576,
            }
        ],
    }


def _prompt_response(
    command_id: str,
    *,
    ended: str = "natural",
    continuation_possible: bool = True,
) -> dict:
    return {
        "type": "response",
        "id": command_id,
        "success": True,
        "data": {
            "ended": ended,
            "loops_started": 1,
            "loops_completed": 1,
            "continuation_possible": continuation_possible,
            "session_id": "sess-1",
            "started_at": "2026-09-11T00:00:00+00:00",
            "ended_at": "2026-09-11T00:00:01+00:00",
            "usage": {"input": 10, "output": 4, "cacheRead": 6},
            "cost": 0.25,
            "quiescence": {"ready": True, "protected_pids": [20]},
        },
    }


def _init_ok(command_id: str) -> dict:
    return {
        "type": "response",
        "id": command_id,
        "success": True,
        "data": {
            "ready": True,
            "session_id": "sess-1",
            "model": "xai-oauth/grok-4.6:medium",
            "protected_pids": [20],
            "policy": {
                "title": False,
                "advisor": False,
                "memory": False,
                "autolearn": False,
                "compaction": False,
                "background_jobs": False,
                # Non-boolean enforcement evidence: a bool-only filter
                # silently dropped exactly these.
                "memory.backend": "off",
                "tools": ["read", "write", "bash"],
            },
        },
    }


class ScriptedDriver:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False
        self.summary_existed_on_close = False
        self.handoff_on_close = False
        self.overwrite_on_turn: str | None = None
        self.overwrite_path: Path | None = None
        self.overwrite_bytes = b"OVERWRITTEN"
        self.logs_dir: Path | None = None

    async def send(self, payload: dict) -> None:
        self.sent.append(json.loads(json.dumps(payload)))
        if (
            payload.get("type") == "prompt"
            and payload.get("turn_id") == self.overwrite_on_turn
            and self.overwrite_path is not None
        ):
            self.overwrite_path.parent.mkdir(parents=True, exist_ok=True)
            self.overwrite_path.write_bytes(self.overwrite_bytes)

    async def recv(self) -> dict:
        raise AssertionError("recv must be wired")

    async def close(self) -> None:
        if self.logs_dir is not None:
            evidence = captures.evidence_dir(self.logs_dir)
            self.summary_existed_on_close = (evidence / "summary.json").is_file()
            handoff = self.logs_dir.parent / "verifier" / "yacht-execution"
            self.handoff_on_close = handoff.exists()
        self.closed = True


class DockerShapedEnvironment:
    """Mirrors the Harbor DockerEnvironment surface the controller uses.

    No host `root`: captures and process snapshots must go through `exec`,
    which here runs the same command a container would, rooted at the
    task workdir.
    """

    def __init__(self, workdir: Path) -> None:
        self.task_env_config = SimpleNamespace(workdir=str(workdir))
        self.default_user = "yacht"
        self.session_id = "smoke__abc__env"
        self.execs: list[str] = []
        self.hidden_present = False

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ):
        del timeout_sec, user
        self.execs.append(command)
        if "/tests" in command or "test.sh" in command or "/solution" in command:
            self.hidden_present = True
            return SimpleNamespace(return_code=0, stdout="", stderr="")
        completed = subprocess.run(
            ["bash", "-c", command],
            cwd=cwd or self.task_env_config.workdir,
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
        )
        return SimpleNamespace(
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


async def _noop_quiesce(**_kwargs) -> None:
    return None


async def _run(
    *,
    workspace: Path,
    logs_dir: Path,
    driver: ScriptedDriver,
    plan: dict | None = None,
    instruction: str = INITIAL,
    env: dict | None = None,
    final_cleanup=_noop_quiesce,
    environment: DockerShapedEnvironment | None = None,
):
    driver.logs_dir = logs_dir
    return await controlled_omp.run_controlled_omp(
        environment=environment or DockerShapedEnvironment(workspace),
        logs_dir=logs_dir,
        instruction=instruction,
        model="xai-oauth/grok-4.6:medium",
        plan=plan or _retained_plan(),
        env=env,
        driver=driver,
        final_cleanup=final_cleanup,
    )


def _wire_success(driver: ScriptedDriver) -> None:
    async def recv() -> dict:
        payload = driver.sent[-1]
        command_id = payload["id"]
        kind = payload["type"]
        if kind == "init":
            return _init_ok(command_id)
        if kind == "prompt":
            return _prompt_response(command_id)
        return {
            "type": "response",
            "id": command_id,
            "success": True,
            "data": {},
        }

    driver.recv = recv  # type: ignore[method-assign]


class FutureScriptIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_future_markers_absent_until_their_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)

            await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            sent = driver.sent
            init = next(item for item in sent if item["type"] == "init")
            self.assertNotIn("turns", init)
            self.assertNotIn("captures", init)
            self.assertNotIn(FUTURE_Q, json.dumps(init))
            self.assertNotIn(FUTURE_X1, json.dumps(init))
            self.assertIn("deadline_ms", init)

            prompts = [item for item in sent if item["type"] == "prompt"]
            self.assertEqual(
                [item["turn_id"] for item in prompts], ["initial", "Q", "X1"]
            )
            self.assertEqual(prompts[0]["message"], INITIAL)
            self.assertNotIn(FUTURE_X1, json.dumps(prompts[1]))
            self.assertEqual(prompts[1]["message"], FUTURE_Q)
            x1_at = next(
                index
                for index, item in enumerate(sent)
                if item.get("type") == "prompt" and item.get("turn_id") == "X1"
            )
            self.assertNotIn(FUTURE_X1, json.dumps(sent[:x1_at]))

    async def test_last_turn_is_followed_by_shutdown_not_another_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)

            await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            types = [item["type"] for item in driver.sent]
            last_prompt = max(
                index for index, kind in enumerate(types) if kind == "prompt"
            )
            after = types[last_prompt + 1 :]
            self.assertNotIn("prompt", after)
            self.assertIn("shutdown", after)

    async def test_retained_does_not_touch_hidden_tests_or_solution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)
            environment = DockerShapedEnvironment(workspace)

            await _run(
                workspace=workspace,
                logs_dir=logs_dir,
                driver=driver,
                environment=environment,
            )

            self.assertFalse(environment.hidden_present)


class ExecutionValidityGuardTests(unittest.TestCase):
    """An invalid controlled run must not read as a completed attempt.

    The host imports the trial outcome and the verifier reward
    separately, so a cold episode that failed init/prompt (or could not
    prove writer cleanup) previously surfaced as completed whenever the
    inter-episode verifier returned a reward. `YachtOmp.run` now raises
    instead of returning normally.

    `agents.py` imports Harbor, which is only present in the launcher
    image, so the guard is exercised through its own source here.
    """

    @staticmethod
    def _guard():
        source = (LAUNCHER_ROOT / "yacht_harbor_agents" / "agents.py").read_text(
            encoding="utf-8"
        )
        start = source.index("class ControlledExecutionInvalid")
        end = source.index("def _utc_now()")
        namespace: dict[str, Any] = {"Any": Any}
        exec(compile(source[start:end], "agents_guard", "exec"), namespace)
        return namespace

    def test_invalid_summary_raises_with_the_recorded_reason(self) -> None:
        guard = self._guard()

        with self.assertRaises(guard["ControlledExecutionInvalid"]) as caught:
            guard["_require_valid_execution"](
                {"valid": False, "ended": "error", "error": "quiescence failed"},
                "controlled cold OMP episodes",
            )

        self.assertIn("quiescence failed", str(caught.exception))
        self.assertIn("controlled cold OMP episodes", str(caught.exception))

    def test_invalid_summary_without_error_still_raises(self) -> None:
        guard = self._guard()

        with self.assertRaises(guard["ControlledExecutionInvalid"]):
            guard["_require_valid_execution"](
                {"valid": False, "ended": "timeout"}, "controlled OMP execution"
            )

    def test_valid_summary_does_not_raise(self) -> None:
        guard = self._guard()

        guard["_require_valid_execution"](
            {"valid": True, "ended": "natural"}, "controlled OMP execution"
        )


class PolicyEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_preserves_non_boolean_policy_evidence(self) -> None:
        """Enforced-settings evidence is the proof of what was disabled.

        A bool-only filter dropped `memory.backend: "off"` and the
        enabled-tools roster, so the summary claimed less enforcement
        than the driver actually reported.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)

            summary = await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            settings = summary["settings"]
            self.assertEqual(settings["memory.backend"], "off")
            self.assertEqual(settings["tools"], ["read", "write", "bash"])
            self.assertFalse(settings["compaction"])
            self.assertFalse(settings["background_jobs"])
            # And the persisted evidence carries the same payload.
            persisted = json.loads(
                (captures.evidence_dir(logs_dir) / "summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(persisted["settings"], settings)


class DeadlineSeamTests(unittest.IsolatedAsyncioTestCase):
    """`deadline_ms` must mean what the driver reads it as.

    `omp_admission.ts` stops a loop when `now() >= overallDeadlineMs`,
    where `now()` is `Date.now()`. So the value must be an absolute
    epoch instant; a duration lands in 1970 and every real prompt
    reports `timeout` before doing any work. This applies the driver's
    own comparison to whatever the controller actually sent instead of
    echoing the payload back.
    """

    async def test_prompt_is_admissible_under_the_drivers_own_comparison(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)
            plan = _retained_plan()
            plan["timeout_seconds"] = 600

            before_ms = time.time() * 1000
            await _run(
                workspace=workspace,
                logs_dir=logs_dir,
                driver=driver,
                plan=plan,
            )
            after_ms = time.time() * 1000

            init = next(item for item in driver.sent if item["type"] == "init")
            overall_deadline_ms = init["deadline_ms"]

            # The driver's admission check, verbatim.
            self.assertFalse(
                after_ms >= overall_deadline_ms,
                "driver would stop the first loop as timeout before any work",
            )
            # And it is the configured budget ahead of now, not a duration.
            self.assertGreaterEqual(overall_deadline_ms, before_ms + 599_000)
            self.assertLessEqual(overall_deadline_ms, after_ms + 601_000)

    async def test_exhausted_wall_budget_is_already_past_the_driver_deadline(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)
            original = driver.recv
            plan = _retained_plan()
            plan["timeout_seconds"] = 1

            async def recv() -> dict:
                frame = await original()
                if driver.sent[-1].get("type") == "prompt":
                    await asyncio.sleep(1.2)
                return frame

            driver.recv = recv  # type: ignore[method-assign]
            summary = await _run(
                workspace=workspace,
                logs_dir=logs_dir,
                driver=driver,
                plan=plan,
            )

            init = next(item for item in driver.sent if item["type"] == "init")
            self.assertGreaterEqual(time.time() * 1000, init["deadline_ms"])
            self.assertEqual(summary["ended"], "timeout")


class CaptureThroughContainerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_uses_exec_not_a_host_root_attribute(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            answers = workspace / "plans" / "retention-answers.json"
            answers.parent.mkdir()
            payload = b'{"q":"exec"}\n'
            answers.write_bytes(payload)
            environment = DockerShapedEnvironment(workspace)
            self.assertFalse(hasattr(environment, "root"))
            driver = ScriptedDriver()
            _wire_success(driver)

            summary = await _run(
                workspace=workspace,
                logs_dir=logs_dir,
                driver=driver,
                environment=environment,
            )

            record = next(item for item in summary["captures"] if item["after"] == "Q")
            self.assertEqual(record["status"], "captured")
            self.assertEqual(record["bytes"], len(payload))
            self.assertEqual(record["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertTrue(
                any("YACHT_CAPTURE_PATH" in command for command in environment.execs)
            )

    async def test_missing_file_in_container_is_missing_not_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)

            summary = await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            record = next(item for item in summary["captures"] if item["after"] == "Q")
            self.assertEqual(record["status"], "missing")
            self.assertTrue(summary["valid"])
            prompts = [item for item in driver.sent if item["type"] == "prompt"]
            self.assertEqual(
                [item["turn_id"] for item in prompts], ["initial", "Q", "X1"]
            )

    async def test_q_capture_survives_later_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            answers = workspace / "plans" / "retention-answers.json"
            answers.parent.mkdir()
            original = b'{"q":"before-x1"}\n'
            answers.write_bytes(original)
            driver = ScriptedDriver()
            driver.overwrite_on_turn = "X1"
            driver.overwrite_path = answers
            _wire_success(driver)

            summary = await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            evidence = captures.evidence_dir(logs_dir)
            record = next(item for item in summary["captures"] if item["after"] == "Q")
            self.assertEqual((evidence / record["artifact"]).read_bytes(), original)
            self.assertEqual(answers.read_bytes(), b"OVERWRITTEN")
            self.assertFalse((logs_dir / record["artifact"]).exists())

    async def test_capture_error_invalidates_and_skips_later_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            (workspace / "plans").mkdir()
            driver = ScriptedDriver()
            _wire_success(driver)
            plan = _retained_plan()
            plan["captures"] = [
                {"id": "Q-0", "after": "Q", "path": "plans", "max_bytes": 1024}
            ]

            summary = await _run(
                workspace=workspace,
                logs_dir=logs_dir,
                driver=driver,
                plan=plan,
            )

            record = next(item for item in summary["captures"] if item["after"] == "Q")
            self.assertEqual(record["status"], "error")
            self.assertFalse(summary["valid"])
            prompts = [item for item in driver.sent if item["type"] == "prompt"]
            self.assertEqual([item["turn_id"] for item in prompts], ["initial", "Q"])


class SettleContractTests(unittest.IsolatedAsyncioTestCase):
    async def _run_with_q_data(
        self, temp_dir: str, mutate
    ) -> tuple[dict, ScriptedDriver]:
        workspace = Path(temp_dir) / "workspace"
        logs_dir = Path(temp_dir) / "trial" / "agent"
        workspace.mkdir()
        logs_dir.mkdir(parents=True)
        driver = ScriptedDriver()
        _wire_success(driver)
        original = driver.recv

        async def recv() -> dict:
            frame = await original()
            payload = driver.sent[-1]
            if payload.get("type") == "prompt" and payload.get("turn_id") == "Q":
                mutate(frame)
            return frame

        driver.recv = recv  # type: ignore[method-assign]
        summary = await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)
        return summary, driver

    async def test_cap_with_continuation_delivers_next_message(self) -> None:
        def mutate(frame: dict) -> None:
            frame["data"]["ended"] = "cap"
            frame["data"]["continuation_possible"] = True

        with tempfile.TemporaryDirectory() as temp_dir:
            summary, driver = await self._run_with_q_data(temp_dir, mutate)

        prompts = [item for item in driver.sent if item["type"] == "prompt"]
        self.assertEqual([item["turn_id"] for item in prompts], ["initial", "Q", "X1"])
        record = next(item for item in summary["messages"] if item["id"] == "Q")
        self.assertEqual(record["ended"], "cap")
        self.assertTrue(summary["valid"])

    async def test_cap_without_continuation_stops_the_script(self) -> None:
        def mutate(frame: dict) -> None:
            frame["data"]["ended"] = "cap"
            frame["data"]["continuation_possible"] = False

        with tempfile.TemporaryDirectory() as temp_dir:
            summary, driver = await self._run_with_q_data(temp_dir, mutate)

        prompts = [item for item in driver.sent if item["type"] == "prompt"]
        self.assertEqual([item["turn_id"] for item in prompts], ["initial", "Q"])
        self.assertEqual(summary["ended"], "cap")

    async def test_invalid_reason_marks_infrastructure_failure(self) -> None:
        def mutate(frame: dict) -> None:
            frame["data"]["invalid"] = {"reason": "compaction"}

        with tempfile.TemporaryDirectory() as temp_dir:
            summary, driver = await self._run_with_q_data(temp_dir, mutate)

        self.assertFalse(summary["valid"])
        self.assertEqual(summary["error"], "compaction")
        prompts = [item for item in driver.sent if item["type"] == "prompt"]
        self.assertEqual([item["turn_id"] for item in prompts], ["initial", "Q"])

    async def test_unready_quiescence_stops_and_invalidates(self) -> None:
        def mutate(frame: dict) -> None:
            frame["data"]["quiescence"] = {"ready": False, "protected_pids": []}

        with tempfile.TemporaryDirectory() as temp_dir:
            summary, driver = await self._run_with_q_data(temp_dir, mutate)

        self.assertFalse(summary["valid"])
        prompts = [item for item in driver.sent if item["type"] == "prompt"]
        self.assertEqual([item["turn_id"] for item in prompts], ["initial", "Q"])

    async def test_numeric_cost_and_native_usage_keys_are_mapped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)

            summary = await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            self.assertEqual(summary["cost_usd"], 0.75)
            self.assertEqual(summary["usage"]["input_tokens"], 30)
            self.assertEqual(summary["usage"]["output_tokens"], 12)
            self.assertEqual(summary["usage"]["cache_read_tokens"], 18)
            self.assertNotIn("input", summary["usage"])

    async def test_unknown_usage_stays_absent_not_zero(self) -> None:
        def mutate(frame: dict) -> None:
            frame["data"]["usage"] = None
            frame["data"]["cost"] = None

        with tempfile.TemporaryDirectory() as temp_dir:
            summary, _driver = await self._run_with_q_data(temp_dir, mutate)

        record = next(item for item in summary["messages"] if item["id"] == "Q")
        self.assertNotIn("usage", record)
        self.assertNotIn("cost_usd", record)


class FailureFinalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_quiescence_failure_invalidates_and_withholds_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)

            async def fail_quiesce(**_kwargs):
                raise controlled_omp.ControlledOmpError("quiescence failed")

            summary = await _run(
                workspace=workspace,
                logs_dir=logs_dir,
                driver=driver,
                final_cleanup=fail_quiesce,
            )

            self.assertFalse(summary["valid"])
            handoff = logs_dir.parent / "verifier" / "yacht-execution"
            self.assertFalse(handoff.exists())
            evidence = captures.evidence_dir(logs_dir)
            self.assertTrue((evidence / "summary.json").is_file())

    async def test_failed_prompt_still_reaps_writers_and_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)
            original = driver.recv
            calls: list[dict] = []

            async def recv() -> dict:
                frame = await original()
                if driver.sent[-1].get("type") == "prompt":
                    frame["success"] = False
                    frame["data"] = {"error": "session lost", "code": "session"}
                return frame

            async def counting_quiesce(**kwargs):
                calls.append(kwargs)

            driver.recv = recv  # type: ignore[method-assign]
            summary = await _run(
                workspace=workspace,
                logs_dir=logs_dir,
                driver=driver,
                final_cleanup=counting_quiesce,
            )

            self.assertFalse(summary["valid"])
            self.assertTrue(calls)
            evidence = captures.evidence_dir(logs_dir)
            self.assertTrue((evidence / "summary.json").is_file())

    async def test_cancellation_persists_invalid_evidence_then_propagates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)
            original = driver.recv

            async def recv() -> dict:
                if driver.sent[-1].get("type") == "prompt":
                    raise asyncio.CancelledError()
                return await original()

            driver.recv = recv  # type: ignore[method-assign]

            with self.assertRaises(asyncio.CancelledError):
                await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            evidence = captures.evidence_dir(logs_dir)
            summary = json.loads((evidence / "summary.json").read_text())
            self.assertFalse(summary["valid"])
            self.assertEqual(summary["error"], "cancelled")
            self.assertTrue(driver.closed)

    async def test_hung_driver_does_not_block_forever(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()

            async def recv() -> dict:
                await asyncio.sleep(60)
                raise AssertionError("unreachable")

            driver.recv = recv  # type: ignore[method-assign]
            plan = _retained_plan()
            plan["timeout_seconds"] = 1

            with self.assertRaises(Exception):
                await asyncio.wait_for(
                    _run(
                        workspace=workspace,
                        logs_dir=logs_dir,
                        driver=driver,
                        plan=plan,
                    ),
                    timeout=20,
                )

            evidence = captures.evidence_dir(logs_dir)
            summary = json.loads((evidence / "summary.json").read_text())
            self.assertFalse(summary["valid"])

    async def test_whole_trial_deadline_stops_further_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)
            original = driver.recv
            plan = _retained_plan()
            plan["timeout_seconds"] = 1

            async def recv() -> dict:
                frame = await original()
                if driver.sent[-1].get("type") == "prompt":
                    await asyncio.sleep(1.2)
                return frame

            driver.recv = recv  # type: ignore[method-assign]
            summary = await _run(
                workspace=workspace,
                logs_dir=logs_dir,
                driver=driver,
                plan=plan,
            )

            prompts = [item for item in driver.sent if item["type"] == "prompt"]
            self.assertEqual([item["turn_id"] for item in prompts], ["initial"])
            self.assertEqual([item["id"] for item in summary["messages"]], ["initial"])
            self.assertEqual(summary["ended"], "timeout")
            self.assertTrue(summary["valid"])
            self.assertTrue(driver.closed)

    async def test_secret_values_are_absent_from_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            escaped_secret = 'secret-"quoted"-é'
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)
            original = driver.recv
            queued = {"sent": False}

            async def recv() -> dict:
                if driver.sent[-1]["type"] == "init" and not queued["sent"]:
                    queued["sent"] = True
                    return {
                        "type": "event",
                        "event": {
                            "type": "agent_start",
                            "env": {"OPENAI_API_KEY": escaped_secret},
                            "message": f"request failed using {escaped_secret}",
                            "headers": {"Authorization": "Bearer unlisted-token"},
                            "author": "Ada",
                            "keyword": "retention",
                            "tokenizer": "fixture-tokenizer",
                        },
                    }
                return await original()

            driver.recv = recv  # type: ignore[method-assign]
            await _run(
                workspace=workspace,
                logs_dir=logs_dir,
                driver=driver,
                env={"OPENAI_API_KEY": escaped_secret, "PI_PROXY": "http://proxy"},
            )

            evidence = captures.evidence_dir(logs_dir)
            blob = "".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in evidence.rglob("*")
                if path.is_file()
            )
            self.assertNotIn(escaped_secret, blob)
            self.assertNotIn(json.dumps(escaped_secret)[1:-1], blob)
            self.assertNotIn("unlisted-token", blob)
            self.assertIn("OPENAI_API_KEY", blob)
            events = [
                json.loads(line)
                for line in (evidence / "events.jsonl").read_text().splitlines()
            ]
            event = next(frame["event"] for frame in events if "event" in frame)
            self.assertEqual(event["author"], "Ada")
            self.assertEqual(event["keyword"], "retention")
            self.assertEqual(event["tokenizer"], "fixture-tokenizer")


class VerifierHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_handoff_carries_manifest_and_bytes_only_after_close(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            answers = workspace / "plans" / "retention-answers.json"
            answers.parent.mkdir()
            payload = b'{"q":"handoff"}\n'
            answers.write_bytes(payload)
            driver = ScriptedDriver()
            _wire_success(driver)

            summary = await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            self.assertTrue(driver.closed)
            self.assertFalse(driver.handoff_on_close)
            handoff = logs_dir.parent / "verifier" / "yacht-execution"
            record = next(item for item in summary["captures"] if item["after"] == "Q")
            self.assertEqual((handoff / record["artifact"]).read_bytes(), payload)
            manifest = json.loads((handoff / "manifest.json").read_text())
            entry = next(item for item in manifest["captures"] if item["after"] == "Q")
            self.assertEqual(entry["status"], "captured")
            self.assertEqual(entry["sha256"], record["sha256"])
            self.assertTrue((handoff / "summary.json").is_file())

    async def test_missing_capture_is_identifiable_in_the_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)

            await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            handoff = logs_dir.parent / "verifier" / "yacht-execution"
            manifest = json.loads((handoff / "manifest.json").read_text())
            entry = next(item for item in manifest["captures"] if item["after"] == "Q")
            self.assertEqual(entry["status"], "missing")
            self.assertEqual(entry["path"], "plans/retention-answers.json")
            self.assertNotIn("artifact", entry)


class ColdCappedEpisodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_awaits_async_driver_factory_per_episode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            drivers: list[ScriptedDriver] = []

            async def factory():
                driver = ScriptedDriver()
                _wire_success(driver)
                drivers.append(driver)
                return driver

            await controlled_omp.run_cold_capped_episodes(
                environment=DockerShapedEnvironment(workspace),
                logs_dir=logs_dir,
                instruction="episode-one",
                model="xai-oauth/grok-4.6:medium",
                episode_plan={
                    "max": 2,
                    "timeout_seconds": 30,
                    "verify_between": False,
                    "instructions": ["episode-two"],
                },
                max_turns=1,
                driver_factory=factory,
                final_cleanup=_noop_quiesce,
            )

            self.assertEqual(len(drivers), 2)
            first = next(item for item in drivers[0].sent if item["type"] == "prompt")
            second = next(item for item in drivers[1].sent if item["type"] == "prompt")
            self.assertEqual(first["message"], "episode-one")
            self.assertEqual(second["message"], "episode-two")

    async def test_verifier_reward_stops_the_relay_early(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            starts: list[str] = []

            async def factory():
                driver = ScriptedDriver()
                _wire_success(driver)
                starts.append("driver")
                return driver

            async def verify_between(index: int, episode_dir: Path):
                del index, episode_dir
                return 1.0

            await controlled_omp.run_cold_capped_episodes(
                environment=DockerShapedEnvironment(workspace),
                logs_dir=logs_dir,
                instruction="episode-one",
                model="xai-oauth/grok-4.6:medium",
                episode_plan={
                    "max": 3,
                    "timeout_seconds": 30,
                    "verify_between": True,
                    "instructions": ["episode-two", "episode-three"],
                },
                max_turns=1,
                driver_factory=factory,
                final_cleanup=_noop_quiesce,
                task_dir=workspace,
                verify_between=verify_between,
            )

            self.assertEqual(len(starts), 1)
            relay = json.loads(
                (logs_dir / "episodes" / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(relay["to_resolution"], 1)
            self.assertEqual(relay["count"], 1)
            self.assertEqual(relay["items"][0]["reward"], 1.0)

    async def test_each_episode_keeps_its_own_evidence_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)

            async def factory():
                driver = ScriptedDriver()
                _wire_success(driver)
                return driver

            await controlled_omp.run_cold_capped_episodes(
                environment=DockerShapedEnvironment(workspace),
                logs_dir=logs_dir,
                instruction="episode-one",
                model="xai-oauth/grok-4.6:medium",
                episode_plan={
                    "max": 2,
                    "timeout_seconds": 30,
                    "verify_between": False,
                    "instructions": ["episode-two"],
                },
                max_turns=1,
                driver_factory=factory,
                final_cleanup=_noop_quiesce,
            )

            private = captures.evidence_dir(logs_dir) / "episodes"
            first = private / "001" / "yacht-execution" / "summary.json"
            second = private / "002" / "yacht-execution" / "summary.json"
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())
            self.assertNotEqual(first.parent, second.parent)
            self.assertEqual(json.loads(first.read_text())["session_ids"], ["sess-1"])
            self.assertEqual(json.loads(second.read_text())["session_ids"], ["sess-1"])


class ProcReapTests(unittest.TestCase):
    def _entry(self, pid: int, ppid: int, starttime: int, cmdline: str) -> dict:
        return {
            "pid": pid,
            "ppid": ppid,
            "starttime": starttime,
            "cmdline": cmdline,
        }

    def test_only_protects_verified_identities_not_matching_commands(self) -> None:
        baseline_entries = [
            self._entry(1, 0, 1, "/sbin/init"),
            self._entry(10, 1, 10, "node /opt/mcp-server.js"),
            self._entry(20, 1, 20, "bun /usr/lib/node_modules/omp_control.ts"),
        ]
        baseline = quiesce.baseline_from_entries(baseline_entries)
        current = baseline_entries + [
            self._entry(30, 20, 30, "sleep 30"),
            self._entry(31, 1, 31, "sh -c sleep 2; echo leaked"),
            self._entry(32, 1, 32, "node /opt/mcp-server.js"),
        ]

        reap = quiesce.reap_from_entries(current, baseline=baseline, protect_pids={20})

        self.assertEqual(set(reap), {(30, 30), (31, 31), (32, 32)})
        self.assertNotIn((1, 1), reap)
        self.assertNotIn((10, 10), reap)
        self.assertNotIn((20, 20), reap)

    def test_recycled_pid_is_reaped_by_identity_not_number(self) -> None:
        baseline = quiesce.baseline_from_entries(
            [self._entry(40, 1, 40, "node /opt/mcp-server.js")]
        )

        reap = quiesce.reap_from_entries(
            [self._entry(40, 1, 99, "sleep 5")],
            baseline=baseline,
            protect_pids=set(),
        )

        self.assertEqual(reap, [(40, 99)])


class ProductionReapTests(unittest.IsolatedAsyncioTestCase):
    async def test_detached_writer_can_mutate_before_next_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            target = workspace / "late-mutation.txt"
            environment = DockerShapedEnvironment(workspace)
            driver = ScriptedDriver()
            _wire_success(driver)
            original_send = driver.send
            spawned: list[subprocess.Popen] = []

            def _close_pipes(process: subprocess.Popen) -> None:
                if process.stdin is not None:
                    process.stdin.close()
                if process.stdout is not None:
                    process.stdout.close()

            with contextlib.ExitStack() as stack:

                async def send(payload: dict) -> None:
                    await original_send(payload)
                    if (
                        payload.get("type") == "prompt"
                        and payload.get("turn_id") == "initial"
                    ):
                        proc = subprocess.Popen(
                            [
                                "sh",
                                "-c",
                                "echo $$; while IFS= read -r cmd; do"
                                ' if [ "$cmd" = mutate ]; then echo leaked > "$1"; echo done; fi;'
                                "done",
                                "writer",
                                str(target),
                            ],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True,
                            text=True,
                        )
                        stack.enter_context(proc)
                        ready = (
                            proc.stdout.readline() if proc.stdout is not None else ""
                        )
                        if not str(ready).strip():
                            proc.kill()
                            proc.wait(timeout=5)
                            _close_pipes(proc)
                            raise AssertionError("writer never advertised readiness")
                        spawned.append(proc)
                    if (
                        payload.get("type") == "prompt"
                        and payload.get("turn_id") == "Q"
                    ):
                        proc = spawned[0]
                        if proc.poll() is not None:
                            raise AssertionError(
                                "writer was killed before the next turn"
                            )
                        if proc.stdin is None or proc.stdout is None:
                            raise AssertionError("writer pipes closed")
                        proc.stdin.write("mutate\n")
                        proc.stdin.flush()
                        if proc.stdout.readline().strip() != "done":
                            raise AssertionError("writer did not acknowledge mutation")

                driver.send = send  # type: ignore[method-assign]

                async def reap_writer(**_kwargs) -> None:
                    for process in spawned:
                        if process.poll() is None:
                            quiesce.kill_process_tree(process.pid)
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=5)
                        _close_pipes(process)

                try:
                    summary = await _run(
                        workspace=workspace,
                        logs_dir=logs_dir,
                        driver=driver,
                        environment=environment,
                        final_cleanup=reap_writer,
                    )
                    self.assertTrue(summary["valid"])
                    self.assertTrue(
                        target.exists(), "late mutation must exist next turn"
                    )
                    self.assertEqual(target.read_text(encoding="utf-8"), "leaked\n")
                    self.assertEqual(summary["session_ids"], ["sess-1"])
                finally:
                    for process in spawned:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=5)
                        _close_pipes(process)


class ContractGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_canonical_validator_is_a_hard_error(self) -> None:
        original = controlled_omp._load_plan_validator

        def boom():
            raise controlled_omp.ControlledOmpError(
                "canonical execution contract is absent"
            )

        controlled_omp._load_plan_validator = boom  # type: ignore[assignment]
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir) / "workspace"
                logs_dir = Path(temp_dir) / "trial" / "agent"
                workspace.mkdir()
                logs_dir.mkdir(parents=True)
                driver = ScriptedDriver()
                _wire_success(driver)

                with self.assertRaises(controlled_omp.ControlledOmpError):
                    await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

                self.assertEqual(driver.sent, [])
        finally:
            controlled_omp._load_plan_validator = original  # type: ignore[assignment]


class CaptureSideEffectTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_leaves_the_source_file_and_tree_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            answers = workspace / "plans" / "retention-answers.json"
            answers.parent.mkdir()
            payload = b'{"q":"untouched"}\n'
            answers.write_bytes(payload)
            answers.chmod(0o640)
            before = answers.stat()
            before_tree = sorted(
                path.relative_to(workspace).as_posix() for path in workspace.rglob("*")
            )
            driver = ScriptedDriver()
            _wire_success(driver)

            await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            after = answers.stat()
            self.assertEqual(after.st_ino, before.st_ino)
            self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
            self.assertEqual(stat.S_IMODE(after.st_mode), 0o640)
            self.assertEqual(answers.read_bytes(), payload)
            self.assertEqual(
                sorted(
                    path.relative_to(workspace).as_posix()
                    for path in workspace.rglob("*")
                ),
                before_tree,
            )

    async def test_capture_of_a_missing_file_creates_no_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)

            await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            self.assertEqual(list(workspace.rglob("*")), [])


class HandoffTruthTests(unittest.IsolatedAsyncioTestCase):
    async def test_late_quiesce_failure_withholds_handoff_despite_earlier_success(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            answers = workspace / "plans" / "retention-answers.json"
            answers.parent.mkdir()
            answers.write_bytes(b'{"q":1}\n')
            driver = ScriptedDriver()
            _wire_success(driver)

            async def fail_cleanup(**_kwargs) -> None:
                raise controlled_omp.ControlledOmpError("writers still running")

            summary = await _run(
                workspace=workspace,
                logs_dir=logs_dir,
                driver=driver,
                final_cleanup=fail_cleanup,
            )

            self.assertFalse(summary["valid"])
            self.assertFalse(
                (logs_dir.parent / "verifier" / "yacht-execution").exists(),
                "final cleanup failure must not publish",
            )

    async def test_final_cleanup_runs_after_close_before_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            answers = workspace / "plans" / "retention-answers.json"
            answers.parent.mkdir()
            answers.write_bytes(b'{"q":1}\n')
            driver = ScriptedDriver()
            _wire_success(driver)
            seen: dict[str, bool] = {}

            async def observe_cleanup(**_kwargs) -> None:
                seen["closed"] = driver.closed
                seen["handoff"] = (
                    logs_dir.parent / "verifier" / "yacht-execution"
                ).exists()

            summary = await _run(
                workspace=workspace,
                logs_dir=logs_dir,
                driver=driver,
                final_cleanup=observe_cleanup,
            )

            self.assertTrue(summary["valid"])
            self.assertTrue(seen.get("closed"))
            self.assertFalse(seen.get("handoff"))
            self.assertTrue((logs_dir.parent / "verifier" / "yacht-execution").exists())
            record = next(item for item in summary["captures"] if item["after"] == "Q")
            self.assertEqual(record["status"], "captured")

    async def test_failed_shutdown_response_invalidates_and_withholds_handoff(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            answers = workspace / "plans" / "retention-answers.json"
            answers.parent.mkdir()
            answers.write_bytes(b'{"q":1}\n')
            driver = ScriptedDriver()
            _wire_success(driver)
            original = driver.recv

            async def recv() -> dict:
                frame = await original()
                if driver.sent[-1].get("type") == "shutdown":
                    frame["success"] = False
                    frame["data"] = {"error": "session disposal failed"}
                return frame

            driver.recv = recv  # type: ignore[method-assign]
            summary = await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            self.assertFalse(summary["valid"])
            self.assertFalse(
                (logs_dir.parent / "verifier" / "yacht-execution").exists(),
                "a driver that cannot dispose of its session must not publish",
            )
            evidence = captures.evidence_dir(logs_dir)
            self.assertTrue((evidence / "summary.json").is_file())

    async def test_unconfirmed_transport_close_withholds_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)
            driver = ScriptedDriver()
            _wire_success(driver)

            async def close() -> None:
                raise RuntimeError("compose client did not exit")

            driver.close = close  # type: ignore[method-assign]
            summary = await _run(workspace=workspace, logs_dir=logs_dir, driver=driver)

            self.assertFalse(
                (logs_dir.parent / "verifier" / "yacht-execution").exists()
            )
            evidence = captures.evidence_dir(logs_dir)
            self.assertTrue((evidence / "summary.json").is_file())
            self.assertEqual(summary["schema"], "yacht.execution.v1")


class ColdEvidencePrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_per_episode_evidence_stays_out_of_the_agent_mount(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            logs_dir = Path(temp_dir) / "trial" / "agent"
            workspace.mkdir()
            logs_dir.mkdir(parents=True)

            async def factory():
                driver = ScriptedDriver()
                _wire_success(driver)
                return driver

            await controlled_omp.run_cold_capped_episodes(
                environment=DockerShapedEnvironment(workspace),
                logs_dir=logs_dir,
                instruction="episode-one",
                model="xai-oauth/grok-4.6:medium",
                episode_plan={
                    "max": 2,
                    "timeout_seconds": 30,
                    "verify_between": False,
                    "instructions": ["episode-two"],
                },
                max_turns=1,
                driver_factory=factory,
                final_cleanup=_noop_quiesce,
            )

            private = captures.evidence_dir(logs_dir) / "episodes"
            self.assertTrue((private / "001" / "yacht-execution").is_dir())
            self.assertTrue((private / "002" / "yacht-execution").is_dir())
            self.assertEqual(
                [
                    path.relative_to(logs_dir).as_posix()
                    for path in logs_dir.rglob("yacht-execution")
                ],
                [],
                "no private evidence directory may sit inside the agent mount",
            )
            self.assertTrue(
                (logs_dir / "episodes" / "summary.json").is_file(),
                "the relay summary stays agent-visible as before",
            )


class RealSnapshotHelperTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the shipped scanner/reap helpers, not an injected stub."""

    def setUp(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is required for the shipped process scanner")

    async def test_scanner_reports_its_own_identity_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            environment = DockerShapedEnvironment(Path(temp_dir))

            entries, own = await controlled_omp._snapshot(environment)

            self.assertTrue(entries)
            self.assertTrue(own)
            identities = {(item["pid"], item["starttime"]) for item in entries}
            self.assertTrue(own.issubset(identities))

    async def test_scanner_identities_never_reach_the_kill_boundary(self) -> None:
        """Scanners the controller spawns must never be signalled.

        Asserts the observable invariant at the signalling boundary
        rather than how many processes an intermediate scan selected: the
        scanner is short-lived, so whether a later scan still sees it is
        timing, not contract. Kills are recorded, never delivered, since
        the shipped reap would signal host PIDs outside a container.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            environment = DockerShapedEnvironment(Path(temp_dir))
            baseline_entries, baseline_own = await controlled_omp._snapshot(environment)
            baseline = quiesce.baseline_from_entries(baseline_entries)
            scanner_identities = set(baseline_own)
            signalled: list[tuple[int, int]] = []

            for _boundary in range(3):
                entries, own = await controlled_omp._snapshot(environment)
                scanner_identities.update(own)
                signalled.extend(
                    identity
                    for identity in quiesce.reap_from_entries(
                        entries, baseline=baseline, protect_pids=set()
                    )
                    if identity not in scanner_identities
                )

            self.assertTrue(scanner_identities)
            self.assertEqual(
                [identity for identity in signalled if identity in scanner_identities],
                [],
                "no scanner identity may reach the kill boundary",
            )


if __name__ == "__main__":
    unittest.main()
