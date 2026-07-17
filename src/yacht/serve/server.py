"""The yacht serve HTTP surface (ADR 0010).

Stdlib only, localhost by default, read-only: every request rescans the
root and renders straight from the artifacts on disk, so the dashboard is
always current and deleting a logbook removes it. Logbooks are addressed
by their directory name relative to the root; names are matched against
discovered entries, never joined to the filesystem, so request paths
cannot escape the root.
"""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from yacht.reports.html_report import render_benchmark_html, render_page
from yacht.serve.collection import (
    LogbookEntry,
    collect_vessel_records,
    discover_logbooks,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9224

ROOT_ENTRY_ID = "."


def respond(root: Path, request_path: str) -> tuple[int, str]:
    """Resolve one request to (status, html body)."""
    path = unquote(urlsplit(request_path).path)
    if path in ("", "/"):
        return 200, _index_page(root)
    parts = [part for part in path.split("/") if part]
    if len(parts) == 2 and parts[0] == "logbook":
        entry = _entry_by_id(root, parts[1])
        if entry is not None:
            return 200, _logbook_page(root, entry)
    return 404, _not_found_page(path)


def run_server(
    *,
    root: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> int:
    discover_logbooks(root)
    server = make_server(root=root, host=host, port=port)
    bound_host, bound_port = server.server_address[:2]
    print(f"Serving YACHT dashboard on http://{bound_host}:{bound_port}/")
    print(f"Logbook root: {root.resolve()}")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def make_server(*, root: Path, host: str, port: int) -> ThreadingHTTPServer:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            status, body = respond(root, self.path)
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            pass

    return ThreadingHTTPServer((host, port), DashboardHandler)


def _entry_id(root: Path, entry: LogbookEntry) -> str:
    if entry.logbook == root:
        return ROOT_ENTRY_ID
    return entry.logbook.name


def _entry_by_id(root: Path, entry_id: str) -> LogbookEntry | None:
    for entry in discover_logbooks(root):
        if _entry_id(root, entry) == entry_id:
            return entry
    return None


def _index_page(root: Path) -> str:
    entries = discover_logbooks(root)
    body = [
        "<h1>YACHT dashboard</h1>",
        f'<p class="sub">Logbook root <code>{_e(str(root.resolve()))}</code> '
        f"&middot; {len(entries)} logbook{'s' if len(entries) != 1 else ''} "
        "&middot; rendered from artifacts on disk</p>",
    ]
    if not entries:
        body.append('<p class="muted">No logbooks found under this root.</p>')
        return render_page("YACHT dashboard", body)
    for (regatta, course), group in _group_entries(entries).items():
        body.append(f"<h2>{_e(regatta)} <code>{_e(course)}</code></h2>")
        body.append(_entries_table(root, group))
    return render_page("YACHT dashboard", body)


def _group_entries(
    entries: list[LogbookEntry],
) -> dict[tuple[str, str], list[LogbookEntry]]:
    groups: dict[tuple[str, str], list[LogbookEntry]] = {}
    for entry in entries:
        key = (entry.regatta or "(unreadable)", entry.course or "")
        groups.setdefault(key, []).append(entry)
    return dict(sorted(groups.items()))


def _entries_table(root: Path, entries: list[LogbookEntry]) -> str:
    rows = [
        "<table><tr><th>Logbook</th><th>Updated</th><th>Status</th>"
        "<th>Problems</th></tr>"
    ]
    for entry in entries:
        entry_id = _entry_id(root, entry)
        status = _entry_status(entry)
        status_class = "fail" if entry.errors else "ok"
        problems = (
            "<br>".join(_e(error) for error in entry.errors)
            if entry.errors
            else '<span class="muted">none</span>'
        )
        rows.append(
            f'<tr><td><a href="/logbook/{_e(entry_id)}">'
            f"<code>{_e(entry_id)}</code></a></td>"
            f"<td>{_e(entry.updated_at)}</td>"
            f'<td class="{status_class}">{_e(status)}</td>'
            f"<td>{problems}</td></tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _entry_status(entry: LogbookEntry) -> str:
    if entry.errors:
        return "broken"
    if entry.benchmark_scorecard is not None:
        return str(entry.benchmark_scorecard.get("status", "unknown"))
    if entry.attempt_scorecard is not None:
        return str(entry.attempt_scorecard.get("status", "unknown"))
    return "no scorecards"


def _logbook_page(root: Path, entry: LogbookEntry) -> str:
    if entry.benchmark_scorecard is not None:
        return render_benchmark_html(
            scorecard=entry.benchmark_scorecard,
            task_attempt_scorecard=entry.attempt_scorecard,
            logbook_dir=entry.logbook,
        )
    body = [f"<h1>{_e(_entry_id(root, entry))}</h1>"]
    body.append(
        f'<p class="sub">Logbook <code>{_e(str(entry.logbook))}</code> '
        f"&middot; updated {_e(entry.updated_at)}</p>"
    )
    if entry.errors:
        body.append("<h2>Broken artifacts</h2><ul>")
        body.extend(f'<li class="fail">{_e(error)}</li>' for error in entry.errors)
        body.append("</ul>")
    if entry.attempt_scorecard is not None:
        body.append("<h2>Task attempts</h2>")
        body.append(_attempts_table(entry))
    body.append('<p><a href="/">&larr; back to all logbooks</a></p>')
    return render_page(f"YACHT: {_entry_id(root, entry)}", body)


def _attempts_table(entry: LogbookEntry) -> str:
    records = collect_vessel_records([entry])
    rows = [
        "<table><tr><th>Comparison</th><th>Vessel</th><th>Status</th>"
        '<th class="num">Attempts</th><th class="num">Tool calls</th>'
        '<th class="num">Tokens</th><th class="num">Duration</th></tr>'
    ]
    for record in records:
        status_class = "ok" if record.status == "measured" else "fail"
        rows.append(
            f"<tr><td>{_e(record.comparison)}</td>"
            f"<td><code>{_e(record.vessel)}</code></td>"
            f'<td class="{status_class}">{_e(record.status)}</td>'
            f'<td class="num">{record.usage["task_attempts"]}</td>'
            f'<td class="num">{record.usage["tool_call_count"]}</td>'
            f'<td class="num">{record.usage["total_tokens"]}</td>'
            f'<td class="num">{record.usage["total_duration_seconds"]:.3f}s</td>'
            "</tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _not_found_page(path: str) -> str:
    body = [
        "<h1>Not found</h1>",
        f'<p class="sub">No dashboard page at <code>{_e(path)}</code>.</p>',
        '<p><a href="/">&larr; back to all logbooks</a></p>',
    ]
    return render_page("YACHT: not found", body)


def _e(value: str) -> str:
    return escape(str(value), quote=True)
