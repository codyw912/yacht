import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


def _load_transport_module():
    module_path = (
        Path(__file__).resolve().parent.parent
        / "containers/harbor-launcher/yacht_harbor_agents/transport.py"
    )
    spec = importlib.util.spec_from_file_location(
        "yacht_harbor_agents_transport",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transport = _load_transport_module()
WORKER_CA_BUNDLE_PATH = transport.WORKER_CA_BUNDLE_PATH
WorkerCaError = transport.WorkerCaError
install_worker_ca = transport.install_worker_ca


class FakeEnvironment:
    def __init__(self, *, chmod_exit_code: int = 0, stderr: str = "") -> None:
        self.chmod_exit_code = chmod_exit_code
        self.stderr = stderr
        self.uploads: list[tuple[Path, str]] = []
        self.commands: list[tuple[str, str | None]] = []

    async def upload_file(self, *, source_path: Path, target_path: str) -> None:
        self.uploads.append((source_path, target_path))

    async def exec(self, *, command: str, user: str | None = None):
        self.commands.append((command, user))
        return SimpleNamespace(
            return_code=self.chmod_exit_code,
            stdout="",
            stderr=self.stderr,
        )


class WorkerCaTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_uploads_then_makes_ca_readable_as_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "worker-ca.crt"
            source.write_text("test CA\n", encoding="utf-8")
            source.chmod(0o600)
            environment = FakeEnvironment()

            await install_worker_ca(environment, str(source))

        self.assertEqual(environment.uploads, [(source, WORKER_CA_BUNDLE_PATH)])
        self.assertEqual(
            environment.commands,
            [(f"chmod 0444 {WORKER_CA_BUNDLE_PATH}", "root")],
        )

    async def test_reports_chmod_failure_after_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "worker-ca.crt"
            source.write_text("test CA\n", encoding="utf-8")
            environment = FakeEnvironment(
                chmod_exit_code=1,
                stderr="permission denied",
            )

            with self.assertRaisesRegex(
                WorkerCaError,
                "failed to make worker CA bundle readable: permission denied",
            ):
                await install_worker_ca(environment, str(source))

        self.assertEqual(environment.uploads, [(source, WORKER_CA_BUNDLE_PATH)])

    async def test_rejects_missing_ca_before_upload(self) -> None:
        environment = FakeEnvironment()

        with self.assertRaisesRegex(WorkerCaError, "worker CA bundle is not readable"):
            await install_worker_ca(environment, "/missing/worker-ca.crt")

        self.assertEqual(environment.uploads, [])
        self.assertEqual(environment.commands, [])
