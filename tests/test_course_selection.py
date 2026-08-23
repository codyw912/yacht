import unittest

from yacht.courses.selection import (
    instance_population_digest,
    instance_rank,
    select_random_instances,
)
from yacht.domain.model import ConfigError


class CourseSelectionTests(unittest.TestCase):
    def test_canonical_sha256_vectors(self) -> None:
        population = ["alpha", "βeta", "task-10", "task-2"]

        self.assertEqual(
            instance_rank("alpha", seed=7).hex(),
            "044c3bf6670d763abb2e7ba71e9fd3ead5f9ad8ada61612b0149989be79d8016",
        )
        self.assertEqual(
            instance_population_digest(population),
            "sha256:310e826bd1ff89a59db22d5ac6e8aa9fbe146cbf7500555a8c36f1619179d5b1",
        )

    def test_selection_is_independent_of_population_order(self) -> None:
        population = ["alpha", "βeta", "task-10", "task-2"]

        selected, provenance = select_random_instances(
            population,
            max_instances=2,
            seed=7,
        )
        reordered, reordered_provenance = select_random_instances(
            reversed(population),
            max_instances=2,
            seed=7,
        )

        self.assertEqual(selected, ("alpha", "task-10"))
        self.assertEqual(reordered, selected)
        self.assertEqual(reordered_provenance, provenance)
        self.assertEqual(
            provenance.to_json(),
            {
                "method": "random",
                "algorithm": "sha256-rank-v1",
                "seed": 7,
                "requested_instances": 2,
                "population_count": 4,
                "population_digest": (
                    "sha256:310e826bd1ff89a59db22d5ac6e8aa9fbe146cbf7500555a8c36f1619179d5b1"
                ),
            },
        )

    def test_seed_changes_the_deterministic_selection(self) -> None:
        population = ["alpha", "βeta", "task-10", "task-2"]

        selected, _ = select_random_instances(population, max_instances=2, seed=8)

        self.assertEqual(selected, ("βeta", "alpha"))

    def test_selection_rejects_sample_larger_than_population(self) -> None:
        with self.assertRaisesRegex(ConfigError, "population size of 1"):
            select_random_instances(["only"], max_instances=2, seed=7)

    def test_selection_rejects_duplicate_ids(self) -> None:
        with self.assertRaisesRegex(ConfigError, r"instance_ids\[1\] is duplicated"):
            select_random_instances(["same", "same"], max_instances=1, seed=7)


if __name__ == "__main__":
    unittest.main()
