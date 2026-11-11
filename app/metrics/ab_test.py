"""A/B farqining statistik ahamiyati (FR-27)."""

import math

from scipy import stats

ALPHA = 0.05


def chi_square(a_yes: int, a_no: int, b_yes: int, b_no: int) -> float | None:
    """k4 uchun χ² mezoni; biror satr yoki ustun boʻsh boʻlsa None."""
    table = [[a_yes, a_no], [b_yes, b_no]]
    if 0 in (a_yes + a_no, b_yes + b_no, a_yes + b_yes, a_no + b_no):
        return None
    return float(stats.chi2_contingency(table).pvalue)


def mann_whitney(a: list[int], b: list[int]) -> float | None:
    """CSAT uchun Mann–Whitney mezoni; namuna boʻsh boʻlsa None."""
    if not a or not b:
        return None
    pvalue = float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    return None if math.isnan(pvalue) else pvalue
