import unittest

from yacht.reports.statistics import (
    GRADE_EVIDENCE,
    GRADE_INSUFFICIENT,
    GRADE_NOT_DISTINGUISHABLE,
    interval_grade,
    min_significant_discordant,
    paired_resolution_statistics,
    sign_test_grade,
    sign_test_p_value,
    t_interval,
    wilson_interval,
)


class WilsonIntervalTests(unittest.TestCase):
    def test_zero_total_has_no_interval(self) -> None:
        self.assertIsNone(wilson_interval(0, 0))

    def test_single_resolved_task_spans_most_of_the_range(self) -> None:
        interval = wilson_interval(1, 1)
        self.assertAlmostEqual(interval["low"], 0.2065, places=3)
        self.assertEqual(interval["high"], 1.0)

    def test_half_resolved_is_centered(self) -> None:
        interval = wilson_interval(5, 10)
        self.assertAlmostEqual(interval["low"], 0.2366, places=3)
        self.assertAlmostEqual(interval["high"], 0.7634, places=3)

    def test_bounds_stay_in_unit_range(self) -> None:
        interval = wilson_interval(0, 3)
        self.assertEqual(interval["low"], 0.0)
        self.assertLess(interval["high"], 1.0)

    def test_rejects_impossible_counts(self) -> None:
        with self.assertRaises(ValueError):
            wilson_interval(4, 3)


class SignTestTests(unittest.TestCase):
    def test_no_discordant_pairs_is_p_one(self) -> None:
        self.assertEqual(sign_test_p_value(0, 0), 1.0)

    def test_balanced_discordance_is_p_one(self) -> None:
        self.assertEqual(sign_test_p_value(3, 3), 1.0)

    def test_exact_values_for_one_sided_sweeps(self) -> None:
        self.assertAlmostEqual(sign_test_p_value(5, 0), 0.0625)
        self.assertAlmostEqual(sign_test_p_value(6, 0), 0.03125)

    def test_minimum_significant_discordant_count_is_six(self) -> None:
        self.assertEqual(min_significant_discordant(), 6)

    def test_grades_follow_the_evidence(self) -> None:
        insufficient = sign_test_grade(1, 0)
        self.assertEqual(insufficient["grade"], GRADE_INSUFFICIENT)
        self.assertEqual(insufficient["min_significant_discordant"], 6)

        noise = sign_test_grade(4, 3)
        self.assertEqual(noise["grade"], GRADE_NOT_DISTINGUISHABLE)
        self.assertGreaterEqual(noise["p_value"], 0.05)

        evidence = sign_test_grade(8, 0)
        self.assertEqual(evidence["grade"], GRADE_EVIDENCE)
        self.assertLess(evidence["p_value"], 0.05)


class TIntervalTests(unittest.TestCase):
    def test_single_value_has_no_interval(self) -> None:
        self.assertIsNone(t_interval([3.0]))

    def test_known_small_sample(self) -> None:
        interval = t_interval([1.0, 2.0, 3.0])
        self.assertAlmostEqual(interval["mean"], 2.0)
        self.assertAlmostEqual(interval["low"], -0.4841, places=3)
        self.assertAlmostEqual(interval["high"], 4.4841, places=3)

    def test_interval_grades(self) -> None:
        self.assertEqual(interval_grade(None), GRADE_INSUFFICIENT)
        self.assertEqual(
            interval_grade({"mean": 2.0, "low": -0.5, "high": 4.5}),
            GRADE_NOT_DISTINGUISHABLE,
        )
        self.assertEqual(
            interval_grade({"mean": 2.0, "low": 0.5, "high": 3.5}),
            GRADE_EVIDENCE,
        )


class PairedResolutionStatisticsTests(unittest.TestCase):
    def test_counts_concordant_and_discordant_tasks(self) -> None:
        statistics = paired_resolution_statistics(
            baseline_resolved_ids=["a", "b", "c"],
            baseline_unresolved_ids=["d", "e"],
            challenger_resolved_ids=["a", "d"],
            challenger_unresolved_ids=["b", "c", "e"],
        )

        self.assertEqual(statistics["shared_tasks"], 5)
        self.assertEqual(statistics["concordant_resolved"], 1)
        self.assertEqual(statistics["concordant_unresolved"], 1)
        self.assertEqual(statistics["discordant_baseline_only"], 2)
        self.assertEqual(statistics["discordant_challenger_only"], 1)
        self.assertEqual(statistics["discordant_baseline_only_ids"], ["b", "c"])
        self.assertEqual(statistics["discordant_challenger_only_ids"], ["d"])
        self.assertEqual(statistics["grade"], GRADE_INSUFFICIENT)

    def test_only_shared_tasks_are_paired(self) -> None:
        statistics = paired_resolution_statistics(
            baseline_resolved_ids=["a", "only-baseline"],
            baseline_unresolved_ids=[],
            challenger_resolved_ids=["a"],
            challenger_unresolved_ids=["only-challenger"],
        )

        self.assertEqual(statistics["shared_tasks"], 1)
        self.assertEqual(statistics["concordant_resolved"], 1)
        self.assertEqual(statistics["discordant_baseline_only"], 0)
        self.assertEqual(statistics["discordant_challenger_only"], 0)
        self.assertEqual(statistics["p_value"], 1.0)


if __name__ == "__main__":
    unittest.main()
