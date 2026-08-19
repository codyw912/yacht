import shutil
import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import ConfigError
from yacht.logbook.index import LogbookState, read_logbook, require_logbook
from yacht.reports.benchmark_status import build_benchmark_status
from yacht.serve.collection import discover_logbooks


_FIXTURES = Path(__file__).parent / "fixtures" / "logbooks"


class LogbookCompatibilityTests(unittest.TestCase):
    def test_scorecard_only_fixture_remains_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = _copy_fixture("scorecard-only", Path(temp_dir))

            snapshot = require_logbook(logbook)
            scorecard = snapshot.artifact("benchmark_scorecard")
            assert scorecard is not None

            self.assertEqual(snapshot.state, LogbookState.LEGACY_SCORECARD_ONLY)
            self.assertTrue(scorecard.present)

    def test_v1_index_fixture_normalizes_historical_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = _copy_fixture("v1-indexed", Path(temp_dir))

            snapshot = require_logbook(logbook)
            wake = snapshot.artifact("real_benchmark_eval")
            assert wake is not None

            self.assertEqual(snapshot.state, LogbookState.HISTORICAL_V1)
            self.assertEqual(
                wake.path,
                (logbook / "wake.json").resolve(),
            )

    def test_v2_partial_and_complete_fixtures_keep_lifecycle_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            partial = _copy_fixture("v2-partial", root, "partial")
            complete = _copy_fixture("v2-complete", root, "complete")

            partial_snapshot = require_logbook(partial)
            complete_snapshot = require_logbook(complete)
            partial_scorecard = partial_snapshot.artifact("benchmark_scorecard")
            complete_wake = complete_snapshot.artifact("real_benchmark_eval")
            assert partial_scorecard is not None
            assert complete_wake is not None

            self.assertEqual(partial_snapshot.status, "running")
            self.assertFalse(partial_scorecard.present)
            self.assertEqual(build_benchmark_status(partial)["status"], "running")
            self.assertEqual(complete_snapshot.status, "complete")
            self.assertTrue(complete_wake.present)

    def test_moved_fixture_resolves_relative_artifact_from_new_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original = _copy_fixture("moved", root, "original")
            moved = root / "relocated"
            original.rename(moved)

            snapshot = require_logbook(moved)
            wake = snapshot.artifact("real_benchmark_eval")
            assert wake is not None

            self.assertEqual(
                wake.path,
                (moved / "nested/wake.json").resolve(),
            )

    def test_malformed_current_fixture_stays_authoritatively_broken(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logbook = _copy_fixture("malformed", Path(temp_dir))

            snapshot = read_logbook(logbook)

            self.assertEqual(snapshot.state, LogbookState.BROKEN)
            with self.assertRaisesRegex(ConfigError, "run index"):
                require_logbook(logbook)

    def test_repetition_fixture_exposes_present_and_missing_children(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logbook = _copy_fixture("repetition", root)

            snapshot = require_logbook(logbook)
            status = build_benchmark_status(logbook)
            entries = discover_logbooks(root)

            self.assertEqual(snapshot.run_kind, "benchmark-repetitions")
            self.assertTrue(snapshot.children[0].present)
            self.assertFalse(snapshot.children[1].present)
            self.assertEqual(status["status"], "blocked")
            self.assertEqual(
                [child["present"] for child in status["children"]],
                [True, False],
            )
            self.assertEqual(len(entries), 2)


def _copy_fixture(name: str, root: Path, destination: str = "logbook") -> Path:
    target = root / destination
    shutil.copytree(_FIXTURES / name, target)
    return target


if __name__ == "__main__":
    unittest.main()
