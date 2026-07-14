import tempfile
import unittest
from pathlib import Path

from yacht.domain.model import ConfigError, load_regatta


class ConfigNameValidationTests(unittest.TestCase):
    def test_accepts_path_safe_names(self) -> None:
        regatta = self._load(
            task_id="django__django-11099",
            vessel_name="pi-container.v2",
            comparison_name="baseline_vs_fff",
        )

        self.assertEqual(regatta.course.tasks[0].id, "django__django-11099")
        self.assertEqual(regatta.vessels[0].name, "pi-container.v2")
        self.assertEqual(regatta.comparisons[0].name, "baseline_vs_fff")

    def test_rejects_task_id_with_path_separator(self) -> None:
        with self.assertRaisesRegex(
            ConfigError,
            r"course task id '\.\./escape' is used in logbook paths",
        ):
            self._load(task_id="../escape")

    def test_rejects_vessel_name_with_path_separator(self) -> None:
        with self.assertRaisesRegex(
            ConfigError,
            r"vessel name 'nested/vessel' is used in logbook paths",
        ):
            self._load(vessel_name="nested/vessel")

    def test_rejects_comparison_name_with_leading_dot(self) -> None:
        with self.assertRaisesRegex(
            ConfigError,
            r"comparison name '\.hidden' is used in logbook paths",
        ):
            self._load(comparison_name=".hidden")

    def test_rejects_adapter_instance_id_with_path_separator(self) -> None:
        config = """
[regatta]
name = "name-validation"

[course]
name = "swe-bench-lite"

[course.adapter]
kind = "swe-bench"
dataset = "SWE-bench/SWE-bench_Lite"
split = "test"
harness = "docker"
instance_ids = ["django__django-11099", "../../escape"]

[[vessels]]
name = "baseline"
model = "mock"
"""
        with self.assertRaisesRegex(
            ConfigError,
            r"course task id '\.\./\.\./escape' is used in logbook paths",
        ):
            self._load_config(config)

    def _load(
        self,
        *,
        task_id: str = "task-1",
        vessel_name: str = "baseline",
        comparison_name: str = "comparison-1",
    ):
        config = f"""
[regatta]
name = "name-validation"

[course]
name = "tiny-course"
tasks = [
  {{ id = "{task_id}", title = "Fix a failing test", difficulty = 1 }},
]

[[vessels]]
name = "{vessel_name}"
model = "mock"

[[vessels]]
name = "challenger"
model = "mock"

[[comparisons]]
name = "{comparison_name}"
course = "tiny-course"
vessels = ["{vessel_name}", "challenger"]
"""
        return self._load_config(config)

    def _load_config(self, config: str):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "regatta.toml"
            config_path.write_text(config, encoding="utf-8")
            return load_regatta(config_path)


if __name__ == "__main__":
    unittest.main()
