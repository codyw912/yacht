import tomllib
import unittest
from pathlib import Path

import yacht


class VersionMetadataTests(unittest.TestCase):
    def test_package_version_matches_project_metadata(self) -> None:
        metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(yacht.__version__, metadata["project"]["version"])


if __name__ == "__main__":
    unittest.main()
