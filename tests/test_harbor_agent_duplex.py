import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


LAUNCHER_ROOT = Path(__file__).resolve().parent.parent / "containers/harbor-launcher"
if str(LAUNCHER_ROOT) not in sys.path:
    sys.path.insert(0, str(LAUNCHER_ROOT))

duplex = importlib.import_module("yacht_harbor_agents.duplex")


class ComposeExecArgvTests(unittest.TestCase):
    def test_uses_sanitized_project_name_overlays_workdir_user_and_no_tty(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_dir = Path(temp_dir) / "environment"
            overlay_a = Path(temp_dir) / "docker-compose-build.yaml"
            overlay_b = Path(temp_dir) / "docker-compose-mounts.json"
            env_dir.mkdir()
            overlay_a.write_text("services: {}\n", encoding="utf-8")
            overlay_b.write_text("{}\n", encoding="utf-8")

            argv = duplex.build_compose_exec_argv(
                session_id="Hello World__abc__env",
                environment_dir=env_dir,
                compose_paths=[overlay_a, overlay_b],
                command="bun /usr/lib/node_modules/omp_control.ts",
                workdir="/workspace",
                user="yacht",
                env={"FOO": "bar"},
            )

            project = argv[argv.index("--project-name") + 1]
            self.assertEqual(project, "hello-world__abc__env")
            self.assertNotRegex(project, r"[A-Z ]")
            self.assertEqual(
                argv[argv.index("--project-directory") + 1],
                str(env_dir.resolve()),
            )
            self.assertEqual(
                argv[argv.index("-f") + 1],
                str(overlay_a.resolve()),
            )
            f_flags = [
                argv[index + 1] for index, item in enumerate(argv) if item == "-f"
            ]
            self.assertEqual(
                f_flags,
                [str(overlay_a.resolve()), str(overlay_b.resolve())],
            )
            exec_at = argv.index("exec")
            self.assertIn(argv[exec_at + 1], ("-T", "--no-TTY"))
            self.assertEqual(argv[argv.index("-w") + 1], "/workspace")
            self.assertEqual(argv[argv.index("-u") + 1], "yacht")
            self.assertIn("FOO=bar", argv)
            self.assertEqual(argv[argv.index("main") - 0], "main")
            self.assertNotIn("hello-world__abc__env-main-1", argv)
            self.assertEqual(
                argv[-3:], ["bash", "-c", "bun /usr/lib/node_modules/omp_control.ts"]
            )
            self.assertNotIn("-it", argv)
            self.assertNotIn("stdin_data", argv)

    def test_leading_underscore_session_id_matches_harbor_sanitizer(self) -> None:
        argv = duplex.build_compose_exec_argv(
            session_id="_Task__env",
            environment_dir=Path("/tmp/env"),
            compose_paths=[],
            command="true",
            workdir=None,
            user=None,
            env=None,
        )

        self.assertEqual(argv[argv.index("--project-name") + 1], "0_task__env")


def _docker_environment(*, windows: bool = False):
    cls = type(
        "DockerEnvironment",
        (),
        {
            "__module__": "harbor.environments.docker.docker",
            "_is_windows_container": windows,
        },
    )
    return cls()


class HarborVersionGateTests(unittest.TestCase):
    def test_rejects_non_docker_environment(self) -> None:
        with self.assertRaises(duplex.DuplexError):
            duplex.require_harbor_docker_linux(
                SimpleNamespace(),
                harbor_version="0.20.0",
            )

    def test_rejects_windows_docker_environment(self) -> None:
        with self.assertRaises(duplex.DuplexError):
            duplex.require_harbor_docker_linux(
                _docker_environment(windows=True),
                harbor_version="0.20.0",
            )

    def test_rejects_harbor_version_other_than_0_20_0(self) -> None:
        with self.assertRaises(duplex.DuplexError):
            duplex.require_harbor_docker_linux(
                _docker_environment(),
                harbor_version="0.19.0",
            )


class DriverPlacementTests(unittest.TestCase):
    def test_driver_sits_beside_npm_root_not_inside_omp_package(self) -> None:
        npm_root = Path("/home/yacht/.nvm/versions/node/v22.11.0/lib/node_modules")
        target = duplex.driver_install_path(npm_root)

        self.assertEqual(target, npm_root / "omp_control.ts")
        self.assertNotIn("@oh-my-pi/pi-coding-agent", target.as_posix())

    def test_launch_command_is_bun_absolute_script_without_future_env(self) -> None:
        script = Path(
            "/home/yacht/.nvm/versions/node/v22.11.0/lib/node_modules/omp_control.ts"
        )
        command, env = duplex.driver_launch(script)

        self.assertEqual(command, f"bun {script}")
        self.assertNotIn("YACHT_TURNS", env or {})
        self.assertNotIn("FUTURE", json.dumps(env or {}))


class BindMountAuditTests(unittest.TestCase):
    def test_allows_default_harbor_log_mounts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir) / "trial"
            trial_dir.mkdir()
            mounts = [
                {
                    "type": "bind",
                    "source": str((trial_dir / "agent").resolve()),
                    "target": "/logs/agent",
                },
                {
                    "type": "bind",
                    "source": str((trial_dir / "verifier").resolve()),
                    "target": "/logs/verifier",
                },
                {
                    "type": "bind",
                    "source": str((trial_dir / "artifacts").resolve()),
                    "target": "/logs/artifacts",
                },
            ]

            duplex.audit_bind_mounts(mounts, trial_dir=trial_dir)

    def test_rejects_bind_of_whole_trial_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir) / "trial"
            trial_dir.mkdir()
            (trial_dir / "yacht-execution").mkdir()
            mounts = [
                {
                    "type": "bind",
                    "source": str(trial_dir.resolve()),
                    "target": "/host-trial",
                }
            ]

            with self.assertRaises(duplex.UnsafeMountError):
                duplex.audit_bind_mounts(mounts, trial_dir=trial_dir)

    def test_rejects_bind_of_private_execution_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir) / "trial"
            evidence = trial_dir / "yacht-execution"
            evidence.mkdir(parents=True)
            mounts = [
                {
                    "type": "bind",
                    "source": str(evidence.resolve()),
                    "target": "/leaked-evidence",
                }
            ]

            with self.assertRaises(duplex.UnsafeMountError):
                duplex.audit_bind_mounts(mounts, trial_dir=trial_dir)

    def test_rejects_task_compose_bind_of_task_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task"
            env_dir = task_dir / "environment"
            env_dir.mkdir(parents=True)
            (task_dir / "task.toml").write_text(
                '[[execution.turns]]\ninstruction = "FUTURE_MARKER"\n',
                encoding="utf-8",
            )
            compose = env_dir / "docker-compose.yaml"
            compose.write_text(
                "services:\n"
                "  main:\n"
                "    volumes:\n"
                f"      - {task_dir}:/task-source:rw\n",
                encoding="utf-8",
            )

            with self.assertRaises(duplex.UnsafeMountError):
                duplex.audit_compose_file(
                    compose,
                    trial_dir=Path(temp_dir) / "trial",
                    task_dir=task_dir,
                )

    def test_rejects_environment_copy_that_includes_task_toml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_dir = Path(temp_dir) / "environment"
            env_dir.mkdir()
            (env_dir / "task.toml").write_text(
                '[[execution.turns]]\nid = "X1"\n',
                encoding="utf-8",
            )

            with self.assertRaises(duplex.UnsafeMountError):
                duplex.audit_environment_dir(env_dir)

    def test_rejects_compose_build_context_escaping_environment_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task"
            env_dir = task_dir / "environment"
            env_dir.mkdir(parents=True)
            (task_dir / "task.toml").write_text(
                '[[execution.turns]]\ninstruction = "FUTURE_MARKER"\n',
                encoding="utf-8",
            )
            compose = env_dir / "docker-compose.yaml"
            compose.write_text(
                "services:\n  main:\n    build: ..\n",
                encoding="utf-8",
            )

            with self.assertRaises(duplex.UnsafeMountError):
                duplex.audit_compose_file(
                    compose,
                    trial_dir=Path(temp_dir) / "trial",
                    task_dir=task_dir,
                )

    def test_rejects_symlinked_build_context_to_task_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task"
            env_dir = task_dir / "environment"
            env_dir.mkdir(parents=True)
            (task_dir / "task.toml").write_text("id = 'X1'\n", encoding="utf-8")
            leak = env_dir / "context"
            leak.symlink_to(task_dir)
            compose = env_dir / "docker-compose.yaml"
            compose.write_text(
                "services:\n  extra:\n    build:\n      context: ./context\n",
                encoding="utf-8",
            )

            with self.assertRaises(duplex.UnsafeMountError):
                duplex.audit_compose_file(
                    compose,
                    trial_dir=Path(temp_dir) / "trial",
                    task_dir=task_dir,
                )


class LineDriverTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_a_frame_larger_than_the_default_64_kib_limit(self) -> None:
        import asyncio

        script = (
            "import json,sys\n"
            "frame = {'type': 'context', 'turn_id': 'Q', "
            "'context': 'x' * (200 * 1024)}\n"
            "sys.stdout.write(json.dumps(frame)+'\\n')\n"
            "sys.stdout.flush()\n"
            "sys.stdin.readline()\n"
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=duplex.MAX_FRAME_BYTES,
        )
        driver = duplex.LineDriver(process)
        try:
            frame = await driver.recv()
            self.assertEqual(frame["turn_id"], "Q")
            self.assertEqual(len(frame["context"]), 200 * 1024)
        finally:
            await driver.close()

    async def test_eof_raises_promptly_instead_of_spinning(self) -> None:
        import asyncio

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "pass",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=duplex.MAX_FRAME_BYTES,
        )
        driver = duplex.LineDriver(process)
        try:
            with self.assertRaises(duplex.DuplexError):
                await asyncio.wait_for(driver.recv(), timeout=10)
        finally:
            await driver.close()

    async def test_stderr_diagnostics_do_not_corrupt_the_protocol_stream(self) -> None:
        import asyncio

        script = (
            "import sys\n"
            "sys.stderr.write('compose warning: ignoring orphan\\n')\n"
            "sys.stderr.flush()\n"
            'sys.stdout.write(\'{"type":"response","id":"1","success":true,"data":{}}\\n\')\n'
            "sys.stdout.flush()\n"
            "sys.stdin.readline()\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            diagnostics = Path(temp_dir) / "driver-stderr.log"
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                script,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=duplex.MAX_FRAME_BYTES,
            )
            driver = duplex.LineDriver(process, diagnostics)
            driver.start_diagnostics()
            try:
                frame = await driver.recv()
                self.assertEqual(frame["id"], "1")
                self.assertTrue(frame["success"])
            finally:
                await driver.close()
            await asyncio.sleep(0.1)
            self.assertIn(
                "compose warning",
                diagnostics.read_text(encoding="utf-8", errors="replace"),
            )


class ResolvedComposeAuditTests(unittest.TestCase):
    """Audits the document Compose actually resolves, not filenames.

    A JSON overlay or an interpolated source reaches the launch argv
    identically to a YAML one, so the audit works on the resolved
    document shape.
    """

    def _audit(self, document, *, temp_dir: str, task_dir: Path) -> None:
        duplex.audit_resolved_compose_document(
            document,
            trial_dir=Path(temp_dir) / "trial",
            task_dir=task_dir,
            project_directory=task_dir / "environment",
        )

    def test_rejects_a_long_syntax_bind_of_the_task_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task"
            (task_dir / "environment").mkdir(parents=True)
            document = {
                "services": {
                    "main": {
                        "volumes": [
                            {
                                "type": "bind",
                                "source": str(task_dir),
                                "target": "/task-source",
                            }
                        ]
                    }
                }
            }

            with self.assertRaises(duplex.UnsafeMountError):
                self._audit(document, temp_dir=temp_dir, task_dir=task_dir)

    def test_rejects_a_direct_bind_of_the_task_toml_itself(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task"
            (task_dir / "environment").mkdir(parents=True)
            future = task_dir / "task.toml"
            future.write_text(
                '[[execution.turns]]\ninstruction = "FUTURE"\n', encoding="utf-8"
            )
            document = {
                "services": {
                    "main": {
                        "volumes": [
                            {
                                "type": "bind",
                                "source": str(future),
                                "target": "/app/task.toml",
                            }
                        ]
                    }
                }
            }

            with self.assertRaises(duplex.UnsafeMountError):
                self._audit(document, temp_dir=temp_dir, task_dir=task_dir)

    def test_rejects_a_resolved_build_context_outside_the_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task"
            env_dir = task_dir / "environment"
            env_dir.mkdir(parents=True)
            (task_dir / "task.toml").write_text("id = 'X1'\n", encoding="utf-8")
            # A symlink inside the environment pointing at the task root.
            (env_dir / "context").symlink_to(task_dir)
            document = {"services": {"builder": {"build": {"context": "./context"}}}}

            with self.assertRaises(duplex.UnsafeMountError):
                self._audit(document, temp_dir=temp_dir, task_dir=task_dir)

    def test_accepts_a_build_context_inside_the_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task"
            env_dir = task_dir / "environment"
            (env_dir / "build").mkdir(parents=True)
            document = {"services": {"builder": {"build": {"context": "./build"}}}}

            self._audit(document, temp_dir=temp_dir, task_dir=task_dir)

    def test_rejects_a_relative_source_resolved_against_the_project_dir(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task"
            (task_dir / "environment").mkdir(parents=True)
            document = {
                "services": {
                    "main": {
                        "volumes": [{"type": "bind", "source": "..", "target": "/t"}]
                    }
                }
            }

            with self.assertRaises(duplex.UnsafeMountError):
                self._audit(document, temp_dir=temp_dir, task_dir=task_dir)

    def test_rejects_a_direct_bind_of_the_private_evidence_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task"
            (task_dir / "environment").mkdir(parents=True)
            evidence = Path(temp_dir) / "trial" / "yacht-execution"
            evidence.mkdir(parents=True)
            document = {
                "services": {
                    "extra": {
                        "volumes": [f"{evidence}:/leaked:ro"],
                    }
                }
            }

            with self.assertRaises(duplex.UnsafeMountError):
                self._audit(document, temp_dir=temp_dir, task_dir=task_dir)

    def test_rejects_unsupported_volume_syntax_rather_than_ignoring_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task"
            (task_dir / "environment").mkdir(parents=True)
            document = {"services": {"main": {"volumes": [12345]}}}

            with self.assertRaises(duplex.UnsafeMountError):
                self._audit(document, temp_dir=temp_dir, task_dir=task_dir)

    def test_accepts_named_volumes_and_default_log_binds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task"
            (task_dir / "environment").mkdir(parents=True)
            trial_dir = Path(temp_dir) / "trial"
            trial_dir.mkdir()
            document = {
                "services": {
                    "main": {
                        "volumes": [
                            {
                                "type": "bind",
                                "source": str((trial_dir / "agent").resolve()),
                                "target": "/logs/agent",
                            },
                            {
                                "type": "volume",
                                "source": "cache",
                                "target": "/cache",
                            },
                        ]
                    }
                }
            }

            self._audit(document, temp_dir=temp_dir, task_dir=task_dir)


if __name__ == "__main__":
    unittest.main()
