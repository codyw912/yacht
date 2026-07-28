"""Statistical evidence for comparison verdicts (ADR 0013).

Everything here is closed-form stdlib arithmetic: Wilson score intervals
for resolution rates, an exact two-sided sign test on discordant pairs
for paired resolution deltas, and t-intervals for means over repeated
runs. Artifacts record the numbers; report surfaces render the grades.
"""

from __future__ import annotations

import math
from typing import Any


CONFIDENCE_LEVEL = 0.95
SIGNIFICANCE_LEVEL = 0.05
_Z_95 = 1.959963984540054

# Planning defaults (ADR 0021). Power is fixed for the same reason the
# confidence level is: one default keeps published artifacts comparable.
# The assumed split is the dial that actually matters, so it is reported
# as a range rather than chosen for the user.
POWER_TARGET = 0.8
PLANNING_SPLITS = (0.9, 0.8, 0.7)
_MAX_PLANNING_PAIRS = 400

GRADE_INSUFFICIENT = "insufficient-evidence"
GRADE_NOT_DISTINGUISHABLE = "not-distinguishable"
GRADE_EVIDENCE = "evidence-of-difference"

# Two-sided 95% critical values of Student's t for df 1..30; the normal
# critical value is used beyond the table.
_T_CRITICAL_95 = (
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
)


def wilson_interval(successes: int, total: int) -> dict[str, float] | None:
    """95% Wilson score interval for a binomial proportion."""
    if total <= 0:
        return None
    if successes < 0 or successes > total:
        raise ValueError("successes must be between 0 and total")
    z_squared = _Z_95 * _Z_95
    rate = successes / total
    denominator = 1.0 + z_squared / total
    center = (rate + z_squared / (2.0 * total)) / denominator
    margin = (
        _Z_95
        * math.sqrt(rate * (1.0 - rate) / total + z_squared / (4.0 * total * total))
        / denominator
    )
    return {
        "low": 0.0 if successes == 0 else max(0.0, center - margin),
        "high": 1.0 if successes == total else min(1.0, center + margin),
    }


def sign_test_p_value(discordant_a: int, discordant_b: int) -> float:
    """Exact two-sided sign test on discordant pairs.

    Under the null hypothesis that neither side is better, each
    discordant pair favors either side with probability one half.
    """
    if discordant_a < 0 or discordant_b < 0:
        raise ValueError("discordant counts must be >= 0")
    total = discordant_a + discordant_b
    if total == 0:
        return 1.0
    extreme = max(discordant_a, discordant_b)
    tail = sum(math.comb(total, k) for k in range(extreme, total + 1))
    p_value = 2.0 * tail * 0.5**total
    return min(1.0, p_value)


def min_significant_discordant() -> int:
    """Smallest discordant-pair count at which the sign test can reach
    significance even when every pair favors one side."""
    total = 1
    while 2.0 * 0.5**total > SIGNIFICANCE_LEVEL:
        total += 1
    return total


def sign_test_grade(discordant_a: int, discordant_b: int) -> dict[str, Any]:
    total = discordant_a + discordant_b
    p_value = sign_test_p_value(discordant_a, discordant_b)
    minimum = min_significant_discordant()
    if total < minimum:
        return {
            "grade": GRADE_INSUFFICIENT,
            "p_value": p_value,
            "min_significant_discordant": minimum,
        }
    if p_value >= SIGNIFICANCE_LEVEL:
        return {"grade": GRADE_NOT_DISTINGUISHABLE, "p_value": p_value}
    return {"grade": GRADE_EVIDENCE, "p_value": p_value}


def sign_test_power(discordant_pairs: int, favored_fraction: float) -> float:
    """Probability the exact sign test reaches significance.

    Assumes each discordant pair favors the challenger independently
    with probability `favored_fraction`. Summed exactly over the
    rejection region, so no normal approximation creeps into planning
    numbers that are already assumption-heavy.
    """
    if discordant_pairs <= 0:
        return 0.0
    if not 0.0 <= favored_fraction <= 1.0:
        raise ValueError("favored_fraction must be between 0 and 1")
    total = discordant_pairs
    power = 0.0
    for favored in range(total + 1):
        if sign_test_p_value(total - favored, favored) < SIGNIFICANCE_LEVEL:
            power += (
                math.comb(total, favored)
                * favored_fraction**favored
                * (1.0 - favored_fraction) ** (total - favored)
            )
    return min(1.0, power)


def min_discordant_for_power(
    favored_fraction: float,
    power_target: float = POWER_TARGET,
) -> int | None:
    """Smallest discordant-pair count reaching the target power.

    None when no count up to the planning ceiling reaches it — a real
    answer for assumed splits close to a coin flip, where the honest
    statement is that this design cannot get there.
    """
    for pairs in range(min_significant_discordant(), _MAX_PLANNING_PAIRS + 1):
        if sign_test_power(pairs, favored_fraction) >= power_target:
            return pairs
    return None


def repetition_budget(
    *,
    discordant_pairs: int,
    shared_tasks: int,
    power_target: float = POWER_TARGET,
    splits: tuple[float, ...] = PLANNING_SPLITS,
) -> dict[str, Any] | None:
    """Plan a fresh run: pairs needed for power, and repetitions to get them.

    Repetition counts scale the pair requirement by this run's observed
    discordance rate, which is itself an estimate — so the rate's Wilson
    interval brackets the answer instead of a single point estimate
    standing in for knowledge nobody has yet.
    """
    if shared_tasks <= 0:
        return None
    rate = discordant_pairs / shared_tasks
    rate_interval = wilson_interval(discordant_pairs, shared_tasks)
    plans = []
    for split in splits:
        pairs_needed = min_discordant_for_power(split, power_target)
        plan: dict[str, Any] = {
            "assumed_favored_fraction": split,
            "discordant_pairs_needed": pairs_needed,
        }
        if pairs_needed is not None:
            plan["repetitions"] = _repetitions_for(pairs_needed, rate, shared_tasks)
            if rate_interval is not None:
                plan["repetitions_range"] = {
                    "low": _repetitions_for(
                        pairs_needed,
                        rate_interval["high"],
                        shared_tasks,
                    ),
                    "high": _repetitions_for(
                        pairs_needed,
                        rate_interval["low"],
                        shared_tasks,
                    ),
                }
        plans.append(plan)
    guidance: dict[str, Any] = {
        "power_target": power_target,
        "significance_level": SIGNIFICANCE_LEVEL,
        "observed_discordance_rate": rate,
        "shared_tasks_per_run": shared_tasks,
        "plans": plans,
        # The budget sizes a new run. Extending this one and re-testing
        # is optional stopping, and its p-value would not mean 0.05.
        "applies_to": "a fresh run committed to in advance",
    }
    if rate_interval is not None:
        guidance["observed_discordance_rate_interval"] = rate_interval
    return guidance


def _repetitions_for(
    pairs_needed: int,
    rate: float,
    shared_tasks: int,
) -> int | None:
    """Repetitions expected to yield the required pairs, or None when the
    rate estimate cannot bound it (a rate of zero implies never)."""
    expected_per_run = rate * shared_tasks
    if expected_per_run <= 0:
        return None
    return math.ceil(pairs_needed / expected_per_run)


def t_interval(values: list[float]) -> dict[str, float] | None:
    """95% t-interval for the mean of a sample; None below two values."""
    count = len(values)
    if count < 2:
        return None
    mean = sum(values) / count
    variance = sum((value - mean) ** 2 for value in values) / (count - 1)
    standard_error = math.sqrt(variance / count)
    degrees_of_freedom = count - 1
    if degrees_of_freedom <= len(_T_CRITICAL_95):
        critical = _T_CRITICAL_95[degrees_of_freedom - 1]
    else:
        critical = _Z_95
    margin = critical * standard_error
    return {
        "mean": mean,
        "low": mean - margin,
        "high": mean + margin,
    }


def interval_grade(interval: dict[str, float] | None) -> str:
    if interval is None:
        return GRADE_INSUFFICIENT
    if interval["low"] <= 0.0 <= interval["high"]:
        return GRADE_NOT_DISTINGUISHABLE
    return GRADE_EVIDENCE


def paired_resolution_statistics(
    *,
    baseline_resolved_ids: list[str],
    baseline_unresolved_ids: list[str],
    challenger_resolved_ids: list[str],
    challenger_unresolved_ids: list[str],
) -> dict[str, Any]:
    baseline_resolved = set(baseline_resolved_ids)
    baseline_attempted = baseline_resolved | set(baseline_unresolved_ids)
    challenger_resolved = set(challenger_resolved_ids)
    challenger_attempted = challenger_resolved | set(challenger_unresolved_ids)
    shared = baseline_attempted & challenger_attempted

    baseline_only = sorted(
        task
        for task in shared
        if task in baseline_resolved and task not in challenger_resolved
    )
    challenger_only = sorted(
        task
        for task in shared
        if task in challenger_resolved and task not in baseline_resolved
    )
    both = sum(
        1
        for task in shared
        if task in baseline_resolved and task in challenger_resolved
    )
    neither = len(shared) - both - len(baseline_only) - len(challenger_only)

    statistics: dict[str, Any] = {
        "shared_tasks": len(shared),
        "concordant_resolved": both,
        "concordant_unresolved": neither,
        "discordant_baseline_only": len(baseline_only),
        "discordant_challenger_only": len(challenger_only),
        "discordant_baseline_only_ids": baseline_only,
        "discordant_challenger_only_ids": challenger_only,
    }
    statistics.update(sign_test_grade(len(baseline_only), len(challenger_only)))
    return statistics
