import pytest

from app.metrics import ahp
from app.metrics.ab_test import chi_square, mann_whitney
from app.metrics.integral import Weights, integral, interpret

CONSISTENT = [[1, 2, 4], [1 / 2, 1, 2], [1 / 4, 1 / 2, 1]]
INCONSISTENT = [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]]


def test_priorities_of_consistent_matrix():
    assert ahp.priorities(CONSISTENT) == pytest.approx([4 / 7, 2 / 7, 1 / 7])


def test_consistent_matrix_has_zero_cr():
    assert ahp.consistency_ratio(CONSISTENT) == pytest.approx(0, abs=1e-9)


def test_inconsistent_matrix_exceeds_limit():
    assert ahp.consistency_ratio(INCONSISTENT) >= ahp.CR_LIMIT


def test_known_cr_value():
    matrix = [[1, 3, 5], [1 / 3, 1, 3], [1 / 5, 1 / 3, 1]]
    assert ahp.priorities(matrix) == pytest.approx([0.6370, 0.2583, 0.1047], abs=1e-3)
    assert ahp.consistency_ratio(matrix) == pytest.approx(0.0332, abs=2e-3)


def test_two_by_two_is_always_consistent():
    assert ahp.consistency_ratio([[1, 7], [1 / 7, 1]]) == 0


def test_reciprocal_matrix():
    assert ahp.reciprocal_matrix(2, {(0, 1): 4.0}) == [[1.0, 4.0], [0.25, 1.0]]


def test_aggregate_is_geometric_mean():
    combined = ahp.aggregate([[[1, 4], [1 / 4, 1]], [[1, 1], [1, 1]]])
    assert combined[0][1] == pytest.approx(2)
    assert combined[1][0] == pytest.approx(1 / 2)


@pytest.mark.parametrize(
    ("value", "label"),
    [
        (0.85, "aʼlo"),
        (0.849, "yaxshi"),
        (0.70, "yaxshi"),
        (0.50, "qoniqarli"),
        (0.499, "past"),
        (None, None),
    ],
)
def test_interpretation(value, label):
    assert interpret(value) == label


WEIGHTS = Weights(
    dimensions={"QD1": 0.5, "QD2": 0.3, "QD3": 0.2},
    local={
        "k1": 0.5,
        "k2": 0.3,
        "k3": 0.2,
        "k4": 0.6,
        "k5": 0.2,
        "k6": 0.2,
        "k7": 0.25,
        "k8": 0.75,
    },
    consistency={},
    experts=1,
)
VALUES = {"k1": 0.9, "k2": 0.8, "k3": 0.7, "k4": 0.6, "k5": 0.5, "k6": 1.0, "k7": 0.4, "k8": 0.8}


def test_integral_by_hand():
    result = integral(VALUES, WEIGHTS)
    assert result["QD1"] == pytest.approx(0.45 + 0.24 + 0.14)
    assert result["QD2"] == pytest.approx(0.36 + 0.1 + 0.2)
    assert result["QD3"] == pytest.approx(0.1 + 0.6)
    assert result["Q"] == pytest.approx(0.5 * 0.83 + 0.3 * 0.66 + 0.2 * 0.7)


def test_overall_weights_sum_to_one():
    assert sum(WEIGHTS.overall(code) for code in WEIGHTS.local) == pytest.approx(1)


def test_missing_indicator_blocks_only_its_dimension():
    result = integral(VALUES | {"k1": None}, WEIGHTS)
    assert result["QD1"] is None
    assert result["QD2"] is not None
    assert result["Q"] is None


def test_no_weights_gives_no_integral():
    assert integral(VALUES, None) == dict.fromkeys(("QD1", "QD2", "QD3", "Q"))


def test_chi_square_known_values():
    assert chi_square(50, 50, 80, 20) < 0.001
    assert chi_square(50, 50, 50, 50) == pytest.approx(1)


def test_chi_square_empty_margin():
    assert chi_square(0, 0, 5, 5) is None
    assert chi_square(5, 0, 5, 0) is None


def test_mann_whitney():
    assert mann_whitney([1, 1, 2, 2, 1, 2] * 5, [5, 4, 5, 4, 5, 5] * 5) < 0.001
    assert mann_whitney([3, 4, 5], [3, 4, 5]) == pytest.approx(1)
    assert mann_whitney([], [1]) is None
