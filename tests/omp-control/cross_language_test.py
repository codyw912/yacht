from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_ROOT = ROOT / "containers" / "harbor-launcher"
if str(LAUNCHER_ROOT) not in sys.path:
    sys.path.insert(0, str(LAUNCHER_ROOT))

controlled_omp = __import__(
    "yacht_harbor_agents.controlled_omp", fromlist=["run_controlled_omp"]
)
duplex = __import__("yacht_harbor_agents.duplex", fromlist=["LineDriver"])

FIRST = "FIRST_USER_MARKER_7c75"
FIRST_ANSWER = "FIRST_ASSISTANT_MARKER_498b"
SECOND = "SECOND_USER_MARKER_e258"
SECOND_ANSWER = "SECOND_ASSISTANT_MARKER_2659"


class FixtureHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length))
        type(self).requests.append(body)
        answer = FIRST_ANSWER if len(type(self).requests) == 1 else SECOND_ANSWER
        chunks = [
            {
                "id": f"chatcmpl-{len(type(self).requests)}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "fixture-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": answer},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": f"chatcmpl-{len(type(self).requests)}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "fixture-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                },
            },
        ]
        payload = (
            "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
            + "data: [DONE]\n\n"
        )
        encoded = payload.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


async def no_host_reap(**kwargs: object) -> None:
    """The fixture creates no task tools; never scan or signal host processes."""
    del kwargs


class CrossLanguageSdkRegression(unittest.IsolatedAsyncioTestCase):
    def test_nested_package_deps_resolve_from_installed_driver(self) -> None:
        bun_env = os.environ.get("YACHT_OMP_BUN")
        self.assertIsNotNone(bun_env, "run through scripts/test_omp_control.sh")
        bun = str(bun_env)
        marker = "YACHT_NESTED_LAYOUT_OK"
        with tempfile.TemporaryDirectory() as temp_dir:
            npm_root = Path(temp_dir) / "node_modules"
            pi_ai = (
                npm_root
                / "@oh-my-pi"
                / "pi-coding-agent"
                / "node_modules"
                / "@oh-my-pi"
                / "pi-ai"
            )
            schema = pi_ai / "utils" / "schema.js"
            schema.parent.mkdir(parents=True)
            (pi_ai / "package.json").write_text(
                json.dumps(
                    {
                        "name": "@oh-my-pi/pi-ai",
                        "type": "module",
                        "exports": {"./utils/schema": "./utils/schema.js"},
                    }
                ),
                encoding="utf-8",
            )
            schema.write_text(
                f'export const YACHT_NESTED_LAYOUT = "{marker}";\n',
                encoding="utf-8",
            )
            driver = duplex.driver_install_path(npm_root)
            driver.parent.mkdir(parents=True, exist_ok=True)
            driver.write_text(
                'import { YACHT_NESTED_LAYOUT } from "@oh-my-pi/pi-ai/utils/schema";\n'
                "console.log(YACHT_NESTED_LAYOUT);\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [bun, "--no-install", str(driver)],
                cwd=driver.parent,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), marker)

    async def test_python_controller_retains_real_sdk_session_over_local_http(
        self,
    ) -> None:
        bun_env = os.environ.get("YACHT_OMP_BUN")
        stage_env = os.environ.get("YACHT_OMP_STAGE_ROOT")
        self.assertIsNotNone(bun_env, "run through scripts/test_omp_control.sh")
        self.assertIsNotNone(stage_env, "run through scripts/test_omp_control.sh")
        bun = str(bun_env)
        driver_path = (
            Path(str(stage_env))
            / "containers/harbor-launcher/yacht_harbor_agents/omp_control.ts"
        )
        FixtureHandler.requests = []
        process: asyncio.subprocess.Process | None = None
        server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                workspace = root / "workspace"
                agent_dir = root / "agent"
                logs_dir = root / "trial" / "agent"
                workspace.mkdir()
                agent_dir.mkdir()
                logs_dir.mkdir(parents=True)
                port = server.server_address[1]
                (agent_dir / "models.yml").write_text(
                    "providers:\n"
                    "  fixture:\n"
                    f"    baseUrl: http://127.0.0.1:{port}/v1\n"
                    "    apiKey: fixture-key\n"
                    "    api: openai-completions\n"
                    "    models:\n"
                    "      - id: fixture-model\n"
                    "        name: Fixture Model\n"
                    "        reasoning: false\n"
                    "        input: [text]\n"
                    "        supportsTools: true\n"
                    "        contextWindow: 32768\n"
                    "        maxTokens: 1024\n"
                )
                child_env = {
                    **os.environ,
                    "HOME": str(root / "home"),
                    "PI_CODING_AGENT_DIR": str(agent_dir),
                    "NO_PROXY": "127.0.0.1,localhost",
                    "no_proxy": "127.0.0.1,localhost",
                }
                process = await asyncio.create_subprocess_exec(
                    bun,
                    "--no-install",
                    str(driver_path),
                    cwd=workspace,
                    env=child_env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                driver = duplex.LineDriver(process, root / "driver-stderr.log")
                driver.start_diagnostics()
                plan = {
                    "mode": "retained",
                    "max_turns": 1,
                    "message_timeout_seconds": 10,
                    "timeout_seconds": 30,
                    "initial_turn_id": "initial",
                    "turns": [{"id": "second", "instruction": SECOND}],
                    "captures": [],
                }
                environment = SimpleNamespace()
                started = time.monotonic()
                summary = await asyncio.wait_for(
                    controlled_omp.run_controlled_omp(
                        environment=environment,
                        logs_dir=logs_dir,
                        instruction=FIRST,
                        model="fixture/fixture-model",
                        plan=plan,
                        driver=driver,
                        quiesce=no_host_reap,
                    ),
                    timeout=45,
                )
                duration = time.monotonic() - started

                self.assertLess(
                    duration, 45, "epoch/duration confusion or shutdown hang"
                )
                self.assertEqual(process.returncode, 0, "driver did not exit cleanly")
                self.assertTrue(summary["valid"])
                self.assertEqual(summary["ended"], "natural")
                self.assertEqual(len(summary["session_ids"]), 1)
                self.assertEqual(
                    [item["id"] for item in summary["messages"]], ["initial", "second"]
                )
                self.assertEqual(len(FixtureHandler.requests), 2)
                second_request = json.dumps(FixtureHandler.requests[1])
                self.assertIn(FIRST, second_request)
                self.assertIn(FIRST_ANSWER, second_request)
                self.assertIn(SECOND, second_request)
                handoff = logs_dir.parent / "verifier" / "yacht-execution"
                manifest = json.loads((handoff / "manifest.json").read_text())
                self.assertTrue(manifest["valid"])
                self.assertEqual(manifest["ended"], "natural")
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
