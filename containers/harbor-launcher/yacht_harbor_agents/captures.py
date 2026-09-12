"""Bounded no-follow captures into private host evidence."""

from __future__ import annotations

import base64
import errno
import hashlib
import json
import os
import shlex
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EVIDENCE_DIRNAME = "yacht-execution"
CAPTURE_EXEC_TIMEOUT_SECONDS = 30

_PYTHON_READER = r"""
import base64, errno, json, os, stat, sys
rel = os.environ["YACHT_CAPTURE_PATH"]
max_bytes = int(os.environ["YACHT_CAPTURE_MAX"])
parts = rel.split("/")
if (not rel or rel.startswith("/") or "\\" in rel
        or any(p in ("", ".", "..") for p in parts)):
    print(json.dumps({"status": "error", "error": "unsafe path"}))
    raise SystemExit(0)
fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
try:
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        flags = os.O_RDONLY | os.O_NOFOLLOW
        if last:
            flags |= os.O_NONBLOCK
        else:
            flags |= os.O_DIRECTORY
        try:
            nxt = os.open(part, flags, dir_fd=fd)
        except FileNotFoundError:
            print(json.dumps({"status": "missing"}))
            raise SystemExit(0)
        except OSError as exc:
            err = "symlink" if exc.errno in (errno.ELOOP, errno.EMLINK) else str(exc)
            print(json.dumps({"status": "error", "error": err}))
            raise SystemExit(0)
        os.close(fd)
        fd = nxt
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        print(json.dumps({"status": "error", "error": "not a file"}))
        raise SystemExit(0)
    chunks = []
    remaining = max_bytes + 1
    while remaining > 0:
        piece = os.read(fd, remaining)
        if not piece:
            break
        chunks.append(piece)
        remaining -= len(piece)
    data = b"".join(chunks)
    if len(data) > max_bytes:
        print(json.dumps({"status": "error", "error": "oversize"}))
        raise SystemExit(0)
    print(json.dumps({"status": "captured", "b64": base64.b64encode(data).decode("ascii")}))
finally:
    try:
        os.close(fd)
    except OSError:
        pass
"""

_NODE_READER = r"""
const fs = require("fs");
const rel = process.env.YACHT_CAPTURE_PATH;
const maxBytes = Number(process.env.YACHT_CAPTURE_MAX);
const parts = rel.split("/");
if (!rel || rel.startsWith("/") || rel.includes("\\")
    || parts.some((p) => p === "" || p === "." || p === "..")) {
  process.stdout.write(JSON.stringify({status: "error", error: "unsafe path"}));
  process.exit(0);
}
let fd;
try {
  fd = fs.openSync(".", "r");
  for (let i = 0; i < parts.length; i++) {
    const last = i === parts.length - 1;
    try {
      // Node has no openat(2). Resolving each component through the
      // previous descriptor's /proc/self/fd entry keeps the walk
      // descriptor-relative, so nested paths resolve correctly and a
      // symlinked parent cannot redirect the walk.
      // O_NONBLOCK keeps a FIFO at the capture path from blocking the
      // open; the fstat below rejects anything not a regular file.
      const nxt = fs.openSync(
        "/proc/self/fd/" + fd + "/" + parts[i],
        fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW
          | (last ? fs.constants.O_NONBLOCK : 0)
      );
      fs.closeSync(fd);
      fd = nxt;
      const st = fs.fstatSync(fd);
      if (!last && !st.isDirectory()) {
        process.stdout.write(JSON.stringify({status: "error", error: "not a file"}));
        process.exit(0);
      }
      if (last) {
        if (!st.isFile()) {
          process.stdout.write(JSON.stringify({status: "error", error: "not a file"}));
          process.exit(0);
        }
        if (st.size > maxBytes) {
          process.stdout.write(JSON.stringify({status: "error", error: "oversize"}));
          process.exit(0);
        }
        const buf = Buffer.alloc(maxBytes + 1);
        const n = fs.readSync(fd, buf, 0, maxBytes + 1, 0);
        if (n > maxBytes) {
          process.stdout.write(JSON.stringify({status: "error", error: "oversize"}));
          process.exit(0);
        }
        process.stdout.write(JSON.stringify({
          status: "captured",
          b64: buf.subarray(0, n).toString("base64"),
        }));
        process.exit(0);
      }
    } catch (exc) {
      const code = exc && exc.code;
      if (code === "ENOENT") {
        process.stdout.write(JSON.stringify({status: "missing"}));
        process.exit(0);
      }
      if (code === "ELOOP" || code === "EPERM" || code === "EMLINK") {
        process.stdout.write(JSON.stringify({status: "error", error: "symlink"}));
        process.exit(0);
      }
      process.stdout.write(JSON.stringify({status: "error", error: String(exc)}));
      process.exit(0);
    }
  }
} finally {
  try { if (fd !== undefined) fs.closeSync(fd); } catch (e) {}
}
"""


@dataclass(frozen=True)
class CaptureRead:
    status: str
    path: str
    data: bytes | None = None
    error: str | None = None


def evidence_dir(logs_dir: Path) -> Path:
    return logs_dir.parent / EVIDENCE_DIRNAME


def is_safe_relative_path(relative_path: str) -> bool:
    if not relative_path or relative_path.startswith("/") or "\\" in relative_path:
        return False
    return all(part not in ("", ".", "..") for part in relative_path.split("/"))


def read_allowlisted_file(
    *, root: Path, relative_path: str, max_bytes: int
) -> CaptureRead:
    if not is_safe_relative_path(relative_path):
        return CaptureRead(status="error", path=relative_path, error="unsafe path")
    try:
        dir_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError:
        return CaptureRead(status="missing", path=relative_path)
    except OSError as error:
        return CaptureRead(status="error", path=relative_path, error=str(error))
    fd = dir_fd
    try:
        parts = relative_path.split("/")
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            flags = os.O_RDONLY | os.O_NOFOLLOW
            if last:
                # A FIFO at the capture path would otherwise block the
                # open forever; the fstat below rejects non-regular files.
                flags |= os.O_NONBLOCK
            else:
                flags |= os.O_DIRECTORY
            try:
                nxt = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                return CaptureRead(status="missing", path=relative_path)
            except OSError as error:
                if error.errno in (errno.ELOOP, errno.EMLINK):
                    return CaptureRead(
                        status="error", path=relative_path, error="symlink"
                    )
                return CaptureRead(status="error", path=relative_path, error=str(error))
            os.close(fd)
            fd = nxt
        info = os.fstat(fd)
        if stat.S_ISLNK(info.st_mode):
            return CaptureRead(status="error", path=relative_path, error="symlink")
        if not stat.S_ISREG(info.st_mode):
            return CaptureRead(status="error", path=relative_path, error="not a file")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            piece = os.read(fd, remaining)
            if not piece:
                break
            chunks.append(piece)
            remaining -= len(piece)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            return CaptureRead(status="error", path=relative_path, error="oversize")
        return CaptureRead(status="captured", path=relative_path, data=data)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def capture_read_command(relative_path: str, max_bytes: int) -> str:
    return (
        "export YACHT_CAPTURE_PATH="
        + shlex.quote(relative_path)
        + "; export YACHT_CAPTURE_MAX="
        + str(int(max_bytes))
        + "; if command -v python3 >/dev/null 2>&1; then python3 -c "
        + shlex.quote(_PYTHON_READER)
        + "; elif command -v node >/dev/null 2>&1; then node -e "
        + shlex.quote(_NODE_READER)
        + '; else echo \'{"status":"error","error":"no capture reader"}\'; fi'
    )


def parse_capture_payload(text: str, relative_path: str) -> CaptureRead:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return CaptureRead(status="error", path=relative_path, error="empty capture")
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return CaptureRead(
            status="error", path=relative_path, error="unreadable capture"
        )
    status = payload.get("status")
    if status == "missing":
        return CaptureRead(status="missing", path=relative_path)
    if status == "captured":
        try:
            data = base64.b64decode(payload.get("b64") or "", validate=False)
        except (ValueError, TypeError):
            return CaptureRead(
                status="error", path=relative_path, error="unreadable capture"
            )
        return CaptureRead(status="captured", path=relative_path, data=data)
    return CaptureRead(
        status="error",
        path=relative_path,
        error=str(payload.get("error") or "error"),
    )


async def capture_via_exec(
    environment: Any,
    *,
    relative_path: str,
    max_bytes: int,
    timeout_seconds: int = CAPTURE_EXEC_TIMEOUT_SECONDS,
) -> CaptureRead:
    if not is_safe_relative_path(relative_path):
        return CaptureRead(status="error", path=relative_path, error="unsafe path")
    workdir = getattr(getattr(environment, "task_env_config", None), "workdir", None)
    try:
        result = await environment.exec(
            command=capture_read_command(relative_path, max_bytes),
            cwd=workdir,
            timeout_sec=timeout_seconds,
        )
    except TypeError:
        # Environments without a timeout parameter still must not hang.
        import asyncio

        result = await asyncio.wait_for(
            environment.exec(
                command=capture_read_command(relative_path, max_bytes),
                cwd=workdir,
            ),
            timeout=timeout_seconds,
        )
    except Exception as error:
        return CaptureRead(status="error", path=relative_path, error=str(error))
    stdout = getattr(result, "stdout", None) or ""
    if getattr(result, "return_code", 0) not in (0, None) and not stdout.strip():
        detail = (getattr(result, "stderr", None) or stdout or "exec failed").strip()
        return CaptureRead(status="error", path=relative_path, error=detail)
    return parse_capture_payload(stdout, relative_path)


def write_host_capture(
    *,
    dest_dir: Path,
    after: str,
    index: int,
    relative_path: str,
    read: CaptureRead,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": f"{after}-{index}",
        "after": after,
        "path": relative_path,
        "status": read.status,
    }
    if read.status != "captured":
        if read.error:
            record["error"] = read.error
        return record
    data = read.data or b""
    digest = hashlib.sha256(data).hexdigest()
    artifact = f"{after}-{index}-{digest[:12]}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / artifact).write_bytes(data)
    record["bytes"] = len(data)
    record["sha256"] = digest
    record["artifact"] = artifact
    return record
