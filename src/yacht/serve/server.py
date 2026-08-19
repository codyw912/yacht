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
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

from yacht.reports.html_report import render_benchmark_html, render_page
from yacht.reports.provenance_format import provenance_mixed
from yacht.serve.collection import (
    LogbookEntry,
    VesselRecord,
    collect_vessel_records,
    discover_logbooks,
)
from yacht.serve.query import (
    FACET_KEYS,
    UNKNOWN_GROUP,
    facet_values,
    filter_records,
    group_records,
)
from yacht.domain.model import ConfigError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9224

ROOT_ENTRY_ID = "."


def respond(root: Path, request_path: str) -> tuple[int, str]:
    """Resolve one request to (status, html body)."""
    split = urlsplit(request_path)
    path = unquote(split.path)
    if path in ("", "/"):
        return 200, _index_page(root)
    parts = [part for part in path.split("/") if part]
    if parts == ["vessels"]:
        try:
            return 200, _vessels_page(root, split.query)
        except ConfigError as error:
            return 400, _bad_request_page(str(error))
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
    body.append(
        '<p><a href="/vessels">All vessel runs</a> &mdash; filter and group '
        "by harness, model, and tool provenance.</p>"
    )
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
        "<table><tr><th>Logbook</th><th>Updated</th><th>Lifecycle</th>"
        "<th>Outcome</th><th>Problems</th></tr>"
    ]
    for entry in entries:
        entry_id = _entry_id(root, entry)
        status = _entry_status(entry)
        outcome = _entry_outcome(entry)
        problems_list = [
            *entry.errors,
            *(f"missing artifact: {artifact}" for artifact in entry.missing_artifacts),
        ]
        status_class = (
            "fail"
            if problems_list
            or status in {"blocked", "failed"}
            or outcome in {"blocked", "failed"}
            else "ok"
        )
        problems = (
            "<br>".join(_e(problem) for problem in problems_list)
            if problems_list
            else '<span class="muted">none</span>'
        )
        rows.append(
            f'<tr><td><a href="/logbook/{_e(entry_id)}">'
            f"<code>{_e(entry_id)}</code></a></td>"
            f"<td>{_e(entry.updated_at)}</td>"
            f'<td class="{status_class}">{_e(status)}</td>'
            f'<td class="{status_class}">{_e(outcome)}</td>'
            f"<td>{problems}</td></tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _entry_status(entry: LogbookEntry) -> str:
    if entry.errors:
        return "broken"
    if entry.status is not None:
        return entry.status
    if entry.benchmark_scorecard is not None:
        return str(entry.benchmark_scorecard.get("status", "unknown"))
    if entry.attempt_scorecard is not None:
        return str(entry.attempt_scorecard.get("status", "unknown"))
    return "no scorecards"


def _entry_outcome(entry: LogbookEntry) -> str:
    return entry.outcome or "unknown"


def _logbook_page(root: Path, entry: LogbookEntry) -> str:
    if entry.benchmark_scorecard is not None:
        return render_benchmark_html(
            scorecard=entry.benchmark_scorecard,
            task_attempt_scorecard=entry.attempt_scorecard,
            logbook_dir=entry.logbook,
            scorecard_path=entry.benchmark_scorecard_path,
        )
    body = [f"<h1>{_e(_entry_id(root, entry))}</h1>"]
    body.append(
        f'<p class="sub">Logbook <code>{_e(str(entry.logbook))}</code> '
        f"&middot; updated {_e(entry.updated_at)} &middot; lifecycle "
        f"<code>{_e(_entry_status(entry))}</code> &middot; outcome "
        f"<code>{_e(_entry_outcome(entry))}</code></p>"
    )
    if entry.errors:
        body.append("<h2>Broken artifacts</h2><ul>")
        body.extend(f'<li class="fail">{_e(error)}</li>' for error in entry.errors)
        body.append("</ul>")
    if entry.missing_artifacts:
        body.append("<h2>Missing artifacts</h2><ul>")
        body.extend(
            f'<li class="fail">{_e(artifact)}</li>'
            for artifact in entry.missing_artifacts
        )
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
        '<th class="num">Attempts</th><th class="num">Distinct tools</th>'
        '<th class="num">Tokens</th><th class="num">Duration</th></tr>'
    ]
    for record in records:
        status_class = "ok" if record.status == "measured" else "fail"
        rows.append(
            f"<tr><td>{_e(record.comparison)}</td>"
            f"<td><code>{_e(record.vessel)}</code></td>"
            f'<td class="{status_class}">{_e(record.status)}</td>'
            f'<td class="num">{record.usage["task_attempts"]}</td>'
            f'<td class="num">{record.usage["distinct_tool_uses"]}</td>'
            f'<td class="num">{record.usage["total_tokens"]}</td>'
            f'<td class="num">{record.usage["total_duration_seconds"]:.3f}s</td>'
            "</tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _vessels_page(root: Path, query: str) -> str:
    filters, group_key = _parse_query(query)
    records = collect_vessel_records(discover_logbooks(root))
    filtered = filter_records(records, filters)
    body = [
        "<h1>Vessel runs</h1>",
        f'<p class="sub">{len(filtered)} of {len(records)} vessel run'
        f"{'s' if len(records) != 1 else ''} across all logbooks "
        '&middot; <a href="/">&larr; all logbooks</a></p>',
    ]
    body.append(_active_filters_section(filters, group_key))
    body.append(_facet_picker_section(filtered, filters, group_key))
    if group_key is not None:
        for value, group in group_records(filtered, group_key).items():
            heading = (
                f"{group_key} = {value}"
                if value != UNKNOWN_GROUP
                else f"{group_key} unknown or mixed"
            )
            body.append(f"<h2>{_e(heading)}</h2>")
            body.append(_group_summary(group))
            body.append(_records_table(root, group))
    else:
        body.append(_group_summary(filtered))
        body.append(_records_table(root, filtered))
    return render_page("YACHT: vessel runs", body)


def _parse_query(query: str) -> tuple[dict[str, str], str | None]:
    params = parse_qs(query, keep_blank_values=False)
    filters = {}
    group_key = None
    for key, values in params.items():
        if key == "group":
            group_key = values[-1]
            continue
        if key not in FACET_KEYS:
            raise ConfigError(
                f"unsupported provenance facet {key}; supported: "
                + ", ".join(FACET_KEYS)
            )
        filters[key] = values[-1]
    if group_key is not None and group_key not in FACET_KEYS:
        raise ConfigError(
            f"unsupported provenance facet {group_key}; supported: "
            + ", ".join(FACET_KEYS)
        )
    return filters, group_key


def _vessels_url(filters: dict[str, str], group_key: str | None) -> str:
    params = dict(sorted(filters.items()))
    if group_key is not None:
        params["group"] = group_key
    if not params:
        return "/vessels"
    return "/vessels?" + urlencode(params)


def _active_filters_section(
    filters: dict[str, str],
    group_key: str | None,
) -> str:
    parts = []
    for key, value in sorted(filters.items()):
        remaining = {k: v for k, v in filters.items() if k != key}
        parts.append(
            f"<code>{_e(key)} = {_e(value)}</code> "
            f'<a href="{_e(_vessels_url(remaining, group_key))}">remove</a>'
        )
    if group_key is not None:
        parts.append(
            f"<code>grouped by {_e(group_key)}</code> "
            f'<a href="{_e(_vessels_url(filters, None))}">ungroup</a>'
        )
    if not parts:
        return ""
    return '<div class="card">Active: ' + " &middot; ".join(parts) + "</div>"


def _facet_picker_section(
    records: list[VesselRecord],
    filters: dict[str, str],
    group_key: str | None,
) -> str:
    rows = []
    for key in FACET_KEYS:
        links = [
            f'<a href="{_e(_vessels_url({**filters, key: value}, group_key))}">'
            f'{_e(value)}</a> <span class="muted">({count})</span>'
            for value, count in facet_values(records, key)
            if filters.get(key) != value
        ]
        group_link = (
            f'<a href="{_e(_vessels_url(filters, key))}">group</a>'
            if group_key != key
            else '<span class="muted">grouped</span>'
        )
        cells = " &middot; ".join(links) if links else '<span class="muted">-</span>'
        rows.append(
            f"<tr><td><code>{_e(key)}</code></td><td>{cells}</td>"
            f"<td>{group_link}</td></tr>"
        )
    return (
        "<h2>Facets</h2><table><tr><th>Facet</th><th>Values</th><th></th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _group_summary(records: list[VesselRecord]) -> str:
    submitted = sum(
        int(record.outcome.get("submitted_instances", 0)) for record in records
    )
    resolved = sum(
        int(record.outcome.get("resolved_instances", 0)) for record in records
    )
    tokens = sum(int(record.usage.get("total_tokens", 0)) for record in records)
    costs = [record.usage.get("total_cost") for record in records]
    cost = (
        sum(float(value) for value in costs if value is not None)
        if all(value is not None for value in costs)
        else None
    )
    rate = f"{resolved / submitted:.3f}" if submitted else "-"
    return (
        f'<p class="sub">{len(records)} vessel run'
        f"{'s' if len(records) != 1 else ''} &middot; "
        f"resolved {resolved}/{submitted} (rate {rate}) &middot; "
        f"{tokens} tokens &middot; cost {_cost(cost)}</p>"
    )


def _records_table(root: Path, records: list[VesselRecord]) -> str:
    rows = [
        "<table><tr><th>Logbook</th><th>Comparison</th><th>Vessel</th>"
        '<th class="num">Resolved</th><th class="num">Tokens</th>'
        '<th class="num">Cost</th><th>Mixed provenance</th></tr>'
    ]
    for record in records:
        logbook_path = Path(record.logbook)
        entry_id = ROOT_ENTRY_ID if logbook_path == root else logbook_path.name
        mixed = provenance_mixed(record.provenance or {})
        mixed_cell = (
            f'<td class="fail">{_e(", ".join(mixed))}</td>'
            if mixed
            else '<td class="muted">none</td>'
        )
        resolved = (
            f"{record.outcome['resolved_instances']}/"
            f"{record.outcome['submitted_instances']}"
            if record.outcome
            else "-"
        )
        rows.append(
            f'<tr><td><a href="/logbook/{_e(entry_id)}">'
            f"<code>{_e(entry_id)}</code></a></td>"
            f"<td>{_e(record.comparison)}</td>"
            f"<td><code>{_e(record.vessel)}</code></td>"
            f'<td class="num">{_e(resolved)}</td>'
            f'<td class="num">{record.usage.get("total_tokens", 0)}</td>'
            f'<td class="num">{_cost(record.usage.get("total_cost"))}</td>'
            f"{mixed_cell}</tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _cost(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value):.6f}"


def _bad_request_page(message: str) -> str:
    body = [
        "<h1>Bad request</h1>",
        f'<p class="sub">{_e(message)}</p>',
        '<p><a href="/vessels">&larr; back to vessel runs</a></p>',
    ]
    return render_page("YACHT: bad request", body)


def _not_found_page(path: str) -> str:
    body = [
        "<h1>Not found</h1>",
        f'<p class="sub">No dashboard page at <code>{_e(path)}</code>.</p>',
        '<p><a href="/">&larr; back to all logbooks</a></p>',
    ]
    return render_page("YACHT: not found", body)


def _e(value: str) -> str:
    return escape(str(value), quote=True)
