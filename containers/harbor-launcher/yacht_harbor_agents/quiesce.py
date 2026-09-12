"""Task-private process baseline and descendant reap."""

from __future__ import annotations

import os
import signal
from dataclasses import dataclass
from pathlib import Path


# A zombie has already exited: it cannot mutate the workspace, but it
# stays visible until its parent reaps it. Treating it as live would
# make the reap loop select it forever and never converge.
ZOMBIE_STATE = "Z"


@dataclass(frozen=True)
class ProcEntry:
    pid: int
    ppid: int
    starttime: int
    cmdline: str
    state: str = ""


@dataclass(frozen=True)
class ProcessBaseline:
    identities: frozenset[tuple[int, int]]
    cmdlines: frozenset[str]


def _parse_stat(text: str) -> tuple[int, int, int, str]:
    rparen = text.rfind(")")
    pid = int(text[: text.find("(")].strip())
    rest = text[rparen + 1 :].split()
    state = rest[0]
    ppid = int(rest[1])
    starttime = int(rest[19])
    return pid, ppid, starttime, state


def iter_proc(proc_root: Path) -> list[ProcEntry]:
    entries: list[ProcEntry] = []
    try:
        children = list(proc_root.iterdir())
    except OSError:
        return entries
    for pid_dir in children:
        if not pid_dir.name.isdigit():
            continue
        try:
            stat_text = (pid_dir / "stat").read_text(encoding="utf-8", errors="replace")
            cmdline = (
                (pid_dir / "cmdline")
                .read_bytes()
                .replace(b"\x00", b" ")
                .decode("utf-8", "replace")
                .strip()
            )
            pid, ppid, starttime, state = _parse_stat(stat_text)
        except (OSError, ValueError, IndexError):
            continue
        entries.append(
            ProcEntry(
                pid=pid,
                ppid=ppid,
                starttime=starttime,
                cmdline=cmdline,
                state=state,
            )
        )
    return entries


def snapshot_process_baseline(proc_root: Path = Path("/proc")) -> ProcessBaseline:
    entries = iter_proc(proc_root)
    return ProcessBaseline(
        identities=frozenset((entry.pid, entry.starttime) for entry in entries),
        cmdlines=frozenset(entry.cmdline for entry in entries if entry.cmdline),
    )


def select_reap_pids(
    proc_root: Path,
    *,
    baseline: ProcessBaseline,
    protect_pids: set[int],
) -> list[int]:
    reap: list[int] = []
    for entry in iter_proc(proc_root):
        if entry.pid == 1:
            continue
        if entry.state == ZOMBIE_STATE:
            continue
        if entry.pid in protect_pids:
            continue
        if (entry.pid, entry.starttime) in baseline.identities:
            continue
        reap.append(entry.pid)
    return reap


def kill_process_tree(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
        return
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


_NODE_SNAPSHOT = r"""
const fs = require("fs");
const entries = [];
const byPid = new Map();
for (const name of fs.readdirSync("/proc")) {
  if (!/^[0-9]+$/.test(name)) continue;
  try {
    const stat = fs.readFileSync("/proc/" + name + "/stat", "utf8");
    const rparen = stat.lastIndexOf(")");
    const rest = stat.slice(rparen + 1).trim().split(/\s+/);
    const cmdline = fs
      .readFileSync("/proc/" + name + "/cmdline")
      .toString("utf8")
      .replace(/\0/g, " ")
      .trim();
    const entry = {
      pid: Number(name),
      ppid: Number(rest[1]),
      starttime: Number(rest[19]),
      state: rest[0],
      cmdline,
    };
    entries.push(entry);
    byPid.set(entry.pid, entry);
  } catch (err) {}
}
// The scanner itself (and the exec chain that started it) must never be
// reaped: it is created after the baseline and would otherwise be
// selected on every scan, so the reap loop could never converge.
const own = [];
let walk = process.pid;
while (walk && walk !== 1 && byPid.has(walk)) {
  const entry = byPid.get(walk);
  own.push([entry.pid, entry.starttime]);
  walk = entry.ppid;
}
process.stdout.write(JSON.stringify({entries, own}));
"""


def baseline_from_entries(entries: list[dict]) -> ProcessBaseline:
    identities = set()
    cmdlines = set()
    for entry in entries:
        identities.add((int(entry["pid"]), int(entry["starttime"])))
        cmdline = str(entry.get("cmdline") or "")
        if cmdline:
            cmdlines.add(cmdline)
    return ProcessBaseline(
        identities=frozenset(identities), cmdlines=frozenset(cmdlines)
    )


def reap_from_entries(
    entries: list[dict],
    *,
    baseline: ProcessBaseline,
    protect_pids: set[int],
) -> list[tuple[int, int]]:
    reap: list[tuple[int, int]] = []
    for entry in entries:
        pid = int(entry["pid"])
        starttime = int(entry["starttime"])
        if pid == 1 or pid in protect_pids:
            continue
        if str(entry.get("state") or "") == ZOMBIE_STATE:
            continue
        if (pid, starttime) in baseline.identities:
            continue
        reap.append((pid, starttime))
    return reap
