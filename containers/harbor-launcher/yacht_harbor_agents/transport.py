"""Worker transport helpers that do not require Harbor at import time."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harbor.environments.base import BaseEnvironment


WORKER_CA_BUNDLE_PATH = "/tmp/yacht-worker-ca-bundle.crt"


class WorkerCaError(RuntimeError):
    pass


async def install_worker_ca(
    environment: BaseEnvironment, source_path: str | None
) -> None:
    if source_path is None:
        return
    source = Path(source_path)
    if not source.is_file():
        raise WorkerCaError(f"worker CA bundle is not readable: {source}")
    await environment.upload_file(
        source_path=source,
        target_path=WORKER_CA_BUNDLE_PATH,
    )
    result = await environment.exec(
        command=f"chmod 0444 {WORKER_CA_BUNDLE_PATH}",
        user="root",
    )
    if result.return_code != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise WorkerCaError(f"failed to make worker CA bundle readable: {detail}")
