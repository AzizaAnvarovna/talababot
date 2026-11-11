"""AHP: geometrik oʻrtacha usulida vaznlar va izchillik (FR-25)."""

import numpy as np

CR_LIMIT = 0.10
_RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41}

Matrix = list[list[float]]


def reciprocal_matrix(size: int, upper: dict[tuple[int, int], float]) -> Matrix:
    matrix = [[1.0] * size for _ in range(size)]
    for (row, column), value in upper.items():
        matrix[row][column] = value
        matrix[column][row] = 1 / value
    return matrix


def priorities(matrix: Matrix) -> list[float]:
    array = np.array(matrix, dtype=float)
    geometric_means = np.prod(array, axis=1) ** (1 / len(array))
    return (geometric_means / geometric_means.sum()).tolist()


def consistency_ratio(matrix: Matrix) -> float:
    array = np.array(matrix, dtype=float)
    size = len(array)
    random_index = _RANDOM_INDEX[size]
    if random_index == 0:
        return 0.0
    weights = np.array(priorities(matrix))
    lambda_max = float(np.mean(array @ weights / weights))
    return max(0.0, (lambda_max - size) / (size - 1) / random_index)


def aggregate(matrices: list[Matrix]) -> Matrix:
    """Ekspertlar matritsalarini element boʻyicha geometrik oʻrtacha bilan birlashtiradi."""
    stacked = np.array(matrices, dtype=float)
    return np.exp(np.mean(np.log(stacked), axis=0)).tolist()
