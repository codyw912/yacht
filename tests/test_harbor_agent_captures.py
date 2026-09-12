import asyncio
import hashlib
import importlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


LAUNCHER_ROOT = Path(__file__).resolve().parent.parent / "containers/harbor-launcher"
if str(LAUNCHER_ROOT) not in sys.path:
    sys.path.insert(0, str(LAUNCHER_ROOT))

captures = importlib.import_module("yacht_harbor_agents.captures")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReadAllowlistedFileTests(unittest.TestCase):
    def test_missing_file_is_missing_and_does_not_mkdir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = captures.read_allowlisted_file(
                root=root,
                relative_path="plans/retention-answers.json",
                max_bytes=1024,
            )

            self.assertEqual(result.status, "missing")
            self.assertIsNone(result.data)
            self.assertFalse((root / "plans").exists())

    def test_empty_file_is_captured_with_zero_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "answers.json"
            path.write_bytes(b"")

            result = captures.read_allowlisted_file(
                root=root,
                relative_path="answers.json",
                max_bytes=1024,
            )

            self.assertEqual(result.status, "captured")
            self.assertEqual(result.data, b"")

    def test_malformed_bytes_are_captured_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = b"{not json\n"
            (root / "answers.json").write_bytes(payload)

            result = captures.read_allowlisted_file(
                root=root,
                relative_path="answers.json",
                max_bytes=1024,
            )

            self.assertEqual(result.status, "captured")
            self.assertEqual(result.data, payload)

    def test_directory_at_capture_path_is_error_not_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "plans").mkdir()

            result = captures.read_allowlisted_file(
                root=root,
                relative_path="plans",
                max_bytes=1024,
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)

    def test_symlink_is_error_and_does_not_follow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outside = Path(temp_dir) / "outside.txt"
            outside.write_bytes(b"secret-target")
            link = root / "answers.json"
            link.symlink_to(outside)

            result = captures.read_allowlisted_file(
                root=root,
                relative_path="answers.json",
                max_bytes=1024,
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)

    def test_rejects_parent_traversal_before_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            root.mkdir()
            secret = Path(temp_dir) / "secret.txt"
            secret.write_bytes(b"host-secret")

            result = captures.read_allowlisted_file(
                root=root,
                relative_path="../secret.txt",
                max_bytes=1024,
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)

    def test_rejects_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            absolute = root / "answers.json"
            absolute.write_bytes(b"nope")

            result = captures.read_allowlisted_file(
                root=root,
                relative_path=str(absolute),
                max_bytes=1024,
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)

    def test_oversize_file_is_error_without_partial_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "answers.json").write_bytes(b"12345")

            result = captures.read_allowlisted_file(
                root=root,
                relative_path="answers.json",
                max_bytes=4,
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)

    def test_exact_max_bytes_is_captured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = b"1234"
            (root / "answers.json").write_bytes(payload)

            result = captures.read_allowlisted_file(
                root=root,
                relative_path="answers.json",
                max_bytes=4,
            )

            self.assertEqual(result.status, "captured")
            self.assertEqual(result.data, payload)


class WriteHostCaptureTests(unittest.TestCase):
    def test_captured_bytes_are_hashed_and_immutable_after_source_overwrite(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            dest = Path(temp_dir) / "yacht-execution"
            root.mkdir()
            dest.mkdir()
            source = root / "plans"
            source.mkdir()
            payload = b'{"q": "original"}\n'
            (source / "retention-answers.json").write_bytes(payload)

            read = captures.read_allowlisted_file(
                root=root,
                relative_path="plans/retention-answers.json",
                max_bytes=1048576,
            )
            record = captures.write_host_capture(
                dest_dir=dest,
                after="Q",
                index=0,
                relative_path="plans/retention-answers.json",
                read=read,
            )
            (source / "retention-answers.json").write_bytes(b'{"q": "overwritten"}')

            self.assertEqual(record["status"], "captured")
            self.assertEqual(record["after"], "Q")
            self.assertEqual(record["path"], "plans/retention-answers.json")
            self.assertEqual(record["bytes"], len(payload))
            self.assertEqual(record["sha256"], _sha256(payload))
            artifact = dest / record["artifact"]
            self.assertEqual(artifact.read_bytes(), payload)
            self.assertNotEqual(
                (source / "retention-answers.json").read_bytes(),
                artifact.read_bytes(),
            )

    def test_missing_does_not_write_an_artifact_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dest = Path(temp_dir) / "yacht-execution"
            dest.mkdir()
            read = captures.read_allowlisted_file(
                root=Path(temp_dir),
                relative_path="plans/retention-answers.json",
                max_bytes=1024,
            )

            record = captures.write_host_capture(
                dest_dir=dest,
                after="Q",
                index=0,
                relative_path="plans/retention-answers.json",
                read=read,
            )

            self.assertEqual(record["status"], "missing")
            self.assertNotIn("artifact", record)
            self.assertEqual(list(dest.iterdir()), [])

    def test_error_is_distinct_from_missing_and_writes_no_captured_bytes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            dest = Path(temp_dir) / "yacht-execution"
            root.mkdir()
            dest.mkdir()
            (root / "plans").mkdir()

            read = captures.read_allowlisted_file(
                root=root,
                relative_path="plans",
                max_bytes=1024,
            )
            record = captures.write_host_capture(
                dest_dir=dest,
                after="Q",
                index=0,
                relative_path="plans",
                read=read,
            )

            self.assertEqual(record["status"], "error")
            self.assertNotEqual(record["status"], "missing")
            self.assertNotIn("sha256", record)
            self.assertEqual([path.name for path in dest.iterdir()], [])

    def test_host_write_does_not_create_or_chmod_the_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            dest = Path(temp_dir) / "yacht-execution"
            root.mkdir()
            dest.mkdir()
            payload = b"abc"
            answers = root / "answers.json"
            answers.write_bytes(payload)
            answers.chmod(0o640)
            before = answers.stat()

            read = captures.read_allowlisted_file(
                root=root,
                relative_path="answers.json",
                max_bytes=1024,
            )
            captures.write_host_capture(
                dest_dir=dest,
                after="Q",
                index=0,
                relative_path="answers.json",
                read=read,
            )

            after = answers.stat()
            self.assertEqual(stat.S_IMODE(after.st_mode), 0o640)
            self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
            self.assertEqual(answers.read_bytes(), payload)
            self.assertNotEqual(dest.resolve(), root.resolve())


class EvidenceLayoutTests(unittest.TestCase):
    def test_evidence_dir_is_sibling_of_agent_logs_not_under_them(self) -> None:
        trial_dir = Path("/tmp/trial-abc")
        logs_dir = trial_dir / "agent"

        evidence = captures.evidence_dir(logs_dir)

        self.assertEqual(evidence, trial_dir / "yacht-execution")
        self.assertEqual(evidence.parent, logs_dir.parent)
        self.assertFalse(str(evidence).startswith(str(logs_dir)))


class BlockingSourceTests(unittest.IsolatedAsyncioTestCase):
    def test_fifo_is_an_error_and_does_not_block_the_local_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            os.mkfifo(root / "answers.json")

            result = captures.read_allowlisted_file(
                root=root,
                relative_path="answers.json",
                max_bytes=1024,
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)

    async def test_fifo_is_an_error_through_exec_without_hanging(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            os.mkfifo(root / "answers.json")
            environment = ExecCaptureTests.ShellEnvironment(root)

            result = await asyncio.wait_for(
                captures.capture_via_exec(
                    environment, relative_path="answers.json", max_bytes=1024
                ),
                timeout=30,
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)


class ParentComponentTests(unittest.TestCase):
    def test_symlinked_parent_directory_does_not_escape_the_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            outside = Path(temp_dir) / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "answers.json").write_bytes(b"host-secret")
            (root / "plans").symlink_to(outside)

            result = captures.read_allowlisted_file(
                root=root,
                relative_path="plans/answers.json",
                max_bytes=1024,
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)


class NodeReaderTests(unittest.IsolatedAsyncioTestCase):
    """The Node fallback runs when the image ships no python3."""

    def setUp(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is required for the fallback capture reader")

    class NodeOnlyEnvironment:
        def __init__(self, workdir: Path) -> None:
            self.task_env_config = SimpleNamespace(workdir=str(workdir))

        async def exec(self, command: str, cwd: str | None = None, **_kwargs):
            # Hide python3 so the command falls through to the Node reader.
            completed = subprocess.run(
                ["bash", "-c", command],
                cwd=cwd or self.task_env_config.workdir,
                capture_output=True,
                text=True,
                env={
                    "PATH": os.path.dirname(shutil.which("node") or "/usr/bin"),
                },
            )
            return SimpleNamespace(
                return_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

    async def test_nested_path_resolves_through_the_parent_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "plans" / "retention-answers.json"
            nested.parent.mkdir()
            payload = b'{"q":"nested"}\n'
            nested.write_bytes(payload)
            # A decoy at the workspace root must not be read instead.
            (root / "retention-answers.json").write_bytes(b"DECOY")
            environment = self.NodeOnlyEnvironment(root)

            result = await captures.capture_via_exec(
                environment,
                relative_path="plans/retention-answers.json",
                max_bytes=1024,
            )

            self.assertEqual(result.status, "captured")
            self.assertEqual(result.data, payload)

    async def test_symlinked_parent_is_rejected_by_the_node_reader(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            outside = Path(temp_dir) / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "answers.json").write_bytes(b"host-secret")
            (root / "plans").symlink_to(outside)
            environment = self.NodeOnlyEnvironment(root)

            result = await captures.capture_via_exec(
                environment, relative_path="plans/answers.json", max_bytes=1024
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)


class ExecCaptureTests(unittest.IsolatedAsyncioTestCase):
    class ShellEnvironment:
        def __init__(self, workdir: Path) -> None:
            self.task_env_config = SimpleNamespace(workdir=str(workdir))
            self.commands: list[str] = []

        async def exec(self, command: str, cwd: str | None = None, **_kwargs):
            self.commands.append(command)
            completed = subprocess.run(
                ["bash", "-c", command],
                cwd=cwd or self.task_env_config.workdir,
                capture_output=True,
                text=True,
            )
            return SimpleNamespace(
                return_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

    async def test_reads_exact_bytes_through_exec(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = b'{"q": "exec-bytes"}\n'
            (root / "answers.json").write_bytes(payload)
            environment = self.ShellEnvironment(root)

            result = await captures.capture_via_exec(
                environment, relative_path="answers.json", max_bytes=1024
            )

            self.assertEqual(result.status, "captured")
            self.assertEqual(result.data, payload)

    async def test_missing_file_through_exec_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            environment = self.ShellEnvironment(Path(temp_dir))

            result = await captures.capture_via_exec(
                environment, relative_path="plans/answers.json", max_bytes=1024
            )

            self.assertEqual(result.status, "missing")
            self.assertFalse((Path(temp_dir) / "plans").exists())

    async def test_oversize_through_exec_is_error_without_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "answers.json").write_bytes(b"0123456789")
            environment = self.ShellEnvironment(root)

            result = await captures.capture_via_exec(
                environment, relative_path="answers.json", max_bytes=4
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)

    async def test_symlink_through_exec_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            root.mkdir()
            secret = Path(temp_dir) / "secret.txt"
            secret.write_bytes(b"host-secret")
            (root / "answers.json").symlink_to(secret)
            environment = self.ShellEnvironment(root)

            result = await captures.capture_via_exec(
                environment, relative_path="answers.json", max_bytes=1024
            )

            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)

    async def test_large_payload_survives_the_exec_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = (b"x" * 1024) * 200
            (root / "big.json").write_bytes(payload)
            environment = self.ShellEnvironment(root)

            result = await captures.capture_via_exec(
                environment, relative_path="big.json", max_bytes=len(payload)
            )

            self.assertEqual(result.status, "captured")
            self.assertEqual(result.data, payload)


if __name__ == "__main__":
    unittest.main()
