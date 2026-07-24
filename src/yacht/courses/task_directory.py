from __future__ import annotations

import hashlib
from pathlib import Path

from yacht.domain.model import ConfigError


def task_directory_digest(path: Path) -> str:
    """Content digest of a local task directory.

    The digest covers every file's repository-relative path and bytes, so
    any change to task content, layout, or file names produces a new
    digest. Runs are comparable when their digests match.
    """
    if not path.is_dir():
        raise ConfigError(f"course adapter task directory not found: {path}")
    files = sorted(
        item for item in path.rglob("*") if item.is_file() and not item.is_symlink()
    )
    if not files:
        raise ConfigError(f"course adapter task directory is empty: {path}")
    digest = hashlib.sha256()
    for item in files:
        relative = item.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(item.read_bytes())
        digest.update(b"\x00")
    return f"sha256:{digest.hexdigest()}"
