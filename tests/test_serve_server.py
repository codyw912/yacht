import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from tests.test_benchmark_aggregate import _write_logbook
from tests.test_serve_collection import _write_v2_index
from yacht.serve.server import make_server, respond


class RespondTests(unittest.TestCase):
    def test_index_lists_logbooks_grouped_by_regatta_and_course(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_logbook(root / "run-1", baseline_resolved=1, fff_resolved=1)
            _write_logbook(root / "run-2", baseline_resolved=0, fff_resolved=1)

            status, body = respond(root, "/")

            self.assertEqual(status, 200)
            self.assertIn("YACHT dashboard", body)
            self.assertIn("pi-fff-comparison", body)
            self.assertIn("swe-bench-lite", body)
            self.assertIn('href="/logbook/run-1"', body)
            self.assertIn('href="/logbook/run-2"', body)
            self.assertIn("2 logbooks", body)

    def test_index_renders_broken_logbooks_visibly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            broken = root / "broken"
            broken.mkdir()
            (broken / "benchmark-scorecard.json").write_text(
                "not json", encoding="utf-8"
            )

            status, body = respond(root, "/")

            self.assertEqual(status, 200)
            self.assertIn('class="fail"', body)
            self.assertIn("broken", body)
            self.assertIn("not valid JSON", body)

    def test_index_renders_index_lifecycle_and_missing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = root / "running"
            logbook.mkdir()
            _write_v2_index(
                logbook,
                {"benchmark_scorecard": "artifacts/benchmark-scorecard.json"},
                status="running",
            )

            status, body = respond(root, "/")

            self.assertEqual(status, 200)
            self.assertIn(">running</td>", body)
            self.assertIn("missing artifact: benchmark_scorecard", body)

    def test_index_with_no_logbooks_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            status, body = respond(Path(temp_dir), "/")

            self.assertEqual(status, 200)
            self.assertIn("No logbooks found", body)

    def test_logbook_page_reuses_benchmark_report_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_logbook(root / "run-1", baseline_resolved=0, fff_resolved=1)

            status, body = respond(root, "/logbook/run-1")

            self.assertEqual(status, 200)
            self.assertIn("pi-fff-comparison", body)
            self.assertIn("verdict", body)
            self.assertIn("pi-plus-fff", body)

    def test_attempt_only_logbook_renders_vessel_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _write_logbook(
                root / "run-1", baseline_resolved=1, fff_resolved=1
            )
            (logbook / "benchmark-scorecard.json").unlink()

            status, body = respond(root, "/logbook/run-1")

            self.assertEqual(status, 200)
            self.assertIn("Task attempts", body)
            self.assertIn("pi-baseline", body)
            self.assertIn("back to all logbooks", body)

    def test_unknown_paths_and_logbooks_return_404(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_logbook(root / "run-1", baseline_resolved=1, fff_resolved=1)

            for path in (
                "/nope",
                "/logbook/run-9",
                "/logbook/run-1/extra",
                "/logbook/%2e%2e",
            ):
                status, body = respond(root, path)
                self.assertEqual(status, 404, path)
                self.assertIn("Not found", body)

    def test_traversal_names_never_reach_the_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_logbook(root / "run-1", baseline_resolved=1, fff_resolved=1)

            status, _ = respond(root, "/logbook/..%2F..%2Fetc%2Fpasswd")

            self.assertEqual(status, 404)

    def test_query_strings_are_ignored_for_routing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_logbook(root / "run-1", baseline_resolved=1, fff_resolved=1)

            status, _ = respond(root, "/?whatever=1")

            self.assertEqual(status, 200)


class VesselsViewTests(unittest.TestCase):
    def _root_with_two_versions(self, temp_dir: str) -> Path:
        root = Path(temp_dir)
        _write_logbook(
            root / "run-1",
            baseline_resolved=1,
            fff_resolved=1,
            harness_version="0.74.0",
        )
        _write_logbook(
            root / "run-2",
            baseline_resolved=0,
            fff_resolved=1,
            harness_version="0.75.0",
        )
        return root

    def test_lists_all_records_with_facet_pickers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root_with_two_versions(temp_dir)

            status, body = respond(root, "/vessels")

            self.assertEqual(status, 200)
            self.assertIn("4 of 4 vessel runs", body)
            self.assertIn("pi 0.74.0", body)
            self.assertIn("pi 0.75.0", body)
            self.assertIn('href="/logbook/run-1"', body)
            self.assertIn("harness.version", body)

    def test_filter_narrows_to_matching_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root_with_two_versions(temp_dir)

            status, body = respond(root, "/vessels?harness.version=pi+0.74.0")

            self.assertEqual(status, 200)
            self.assertIn("2 of 4 vessel runs", body)
            self.assertIn("remove</a>", body)
            self.assertNotIn('href="/logbook/run-2"', body)

    def test_name_filter_matches_across_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root_with_two_versions(temp_dir)

            status, body = respond(root, "/vessels?harness=pi")

            self.assertEqual(status, 200)
            self.assertIn("4 of 4 vessel runs", body)

    def test_grouping_renders_a_section_per_facet_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root_with_two_versions(temp_dir)

            status, body = respond(root, "/vessels?group=harness.version")

            self.assertEqual(status, 200)
            self.assertIn("harness.version = pi 0.74.0", body)
            self.assertIn("harness.version = pi 0.75.0", body)
            self.assertIn("ungroup</a>", body)

    def test_records_without_provenance_group_as_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_logbook(root / "run-1", baseline_resolved=1, fff_resolved=1)

            status, body = respond(root, "/vessels?group=harness.version")

            self.assertEqual(status, 200)
            self.assertIn("harness.version unknown or mixed", body)

    def test_unknown_facet_key_is_a_bad_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root_with_two_versions(temp_dir)

            for query in ("harness.minor=2", "group=harness.minor"):
                status, body = respond(root, f"/vessels?{query}")
                self.assertEqual(status, 400, query)
                self.assertIn("unsupported provenance facet", body)

    def test_group_summary_reports_resolution_and_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._root_with_two_versions(temp_dir)

            status, body = respond(root, "/vessels?harness.version=pi+0.74.0")

            self.assertEqual(status, 200)
            self.assertIn("resolved 2/2 (rate 1.000)", body)

    def test_unreported_cost_is_not_rendered_as_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _write_logbook(
                root / "run-1",
                baseline_resolved=1,
                fff_resolved=1,
            )
            scorecard_path = logbook / "task-attempt-scorecard.json"
            scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
            scorecard["comparisons"][0]["vessels"][1]["cost_sources"] = ["unreported"]
            scorecard_path.write_text(
                json.dumps(scorecard) + "\n",
                encoding="utf-8",
            )

            status, body = respond(root, "/vessels")

            self.assertEqual(status, 200)
            self.assertIn("cost -", body)
            self.assertNotIn(">0.000000<", body)


class HttpServerTests(unittest.TestCase):
    def test_real_server_serves_index_over_http(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_logbook(root / "run-1", baseline_resolved=1, fff_resolved=1)
            server = make_server(root=root, host="127.0.0.1", port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address[:2]
                connection = http.client.HTTPConnection(str(host), int(port))
                connection.request("GET", "/")
                response = connection.getresponse()
                body = response.read().decode("utf-8")

                self.assertEqual(response.status, 200)
                self.assertEqual(
                    response.getheader("Content-Type"),
                    "text/html; charset=utf-8",
                )
                self.assertIn("YACHT dashboard", body)
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
