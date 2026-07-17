import http.client
import tempfile
import threading
import unittest
from pathlib import Path

from tests.test_benchmark_aggregate import _write_logbook
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
