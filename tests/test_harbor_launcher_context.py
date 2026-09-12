import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_DIR = REPO_ROOT / "containers/harbor-launcher"


def _load_prepare_context():
    spec = importlib.util.spec_from_file_location(
        "yacht_launcher_prepare_context", LAUNCHER_DIR / "prepare_context.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare_context = _load_prepare_context()


class StagingSafetyTests(unittest.TestCase):
    def test_stages_launcher_with_the_canonical_validator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "context"

            prepare_context.stage(output)

            staged = output / "yacht_harbor_agents" / "execution_contract.py"
            canonical = REPO_ROOT / "src" / "yacht" / "_execution_contract.py"
            self.assertEqual(staged.read_bytes(), canonical.read_bytes())
            self.assertTrue((output / "Dockerfile").is_file())
            self.assertTrue(
                (output / "yacht_harbor_agents" / "controlled_omp.py").is_file()
            )
            self.assertTrue(
                (output / "yacht_harbor_agents" / "omp_control.ts").is_file()
            )
            self.assertTrue((output / prepare_context.STAGING_MARKER).is_file())

    def test_refuses_an_existing_unowned_directory_without_deleting_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "precious"
            output.mkdir()
            keeper = output / "keep.txt"
            keeper.write_text("user data\n", encoding="utf-8")

            with self.assertRaises(SystemExit):
                prepare_context.stage(output)

            self.assertEqual(keeper.read_text(encoding="utf-8"), "user data\n")

    def test_reuses_a_marker_owned_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "context"
            prepare_context.stage(output)
            stale = output / "stale.txt"
            stale.write_text("old\n", encoding="utf-8")

            prepare_context.stage(output)

            self.assertFalse(stale.exists())
            self.assertTrue((output / "Dockerfile").is_file())

    def test_refuses_to_stage_into_repository_or_launcher_source(self) -> None:
        for target in (REPO_ROOT, LAUNCHER_DIR, LAUNCHER_DIR / "yacht_harbor_agents"):
            with self.assertRaises(SystemExit):
                prepare_context.stage(target)
        self.assertTrue((LAUNCHER_DIR / "Dockerfile").is_file())


if __name__ == "__main__":
    unittest.main()
