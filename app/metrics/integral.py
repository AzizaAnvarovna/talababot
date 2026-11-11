"""Qisman indekslar, integral indeks Q va talqin (TZ 4.8.1, FR-26)."""

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AhpJudgment
from app.metrics import ahp

LABELS = {
    "k1": "k1 — Intent aniqlash sifati",
    "k2": "k2 — Javob mosligi",
    "k3": "k3 — Tushunish darajasi",
    "k4": "k4 — Vazifa bajarilishi",
    "k5": "k5 — Mustaqillik",
    "k6": "k6 — Dialog tejamkorligi",
    "k7": "k7 — Tezkorlik",
    "k8": "k8 — Qoniqish (CSAT)",
    "kS": "kS — Hissiy koʻrsatkich",
    "QD1": "QD1 — Tushunish",
    "QD2": "QD2 — Samaradorlik",
    "QD3": "QD3 — Tajriba",
    "Q": "Q — Integral indeks",
}
DIMENSIONS = {"QD1": ("k1", "k2", "k3"), "QD2": ("k4", "k5", "k6"), "QD3": ("k7", "k8")}
# ahp_judgments.level -> shu matritsada solishtiriladigan elementlar
LEVELS = {0: tuple(DIMENSIONS), 1: DIMENSIONS["QD1"], 2: DIMENSIONS["QD2"], 3: DIMENSIONS["QD3"]}
_SCALE = ((0.85, "aʼlo"), (0.70, "yaxshi"), (0.50, "qoniqarli"))


@dataclass
class Weights:
    dimensions: dict[str, float]
    local: dict[str, float]
    consistency: dict[int, float]
    experts: int

    def overall(self, code: str) -> float:
        dimension = next(name for name, codes in DIMENSIONS.items() if code in codes)
        return self.dimensions[dimension] * self.local[code]


def interpret(value: float | None) -> str | None:
    if value is None:
        return None
    return next((label for limit, label in _SCALE if value >= limit), "past")


def load_weights(db: Session) -> Weights | None:
    judgments = db.scalars(select(AhpJudgment)).all()
    by_level: dict[int, list] = {level: [] for level in LEVELS}
    for judgment in judgments:
        by_level[judgment.level].append(json.loads(judgment.matrix_json))
    if not all(by_level.values()):
        return None

    combined = {level: ahp.aggregate(matrices) for level, matrices in by_level.items()}
    results = {level: ahp.priorities(matrix) for level, matrix in combined.items()}
    return Weights(
        dimensions=dict(zip(LEVELS[0], results[0], strict=True)),
        local={
            code: weight
            for level in (1, 2, 3)
            for code, weight in zip(LEVELS[level], results[level], strict=True)
        },
        consistency={level: ahp.consistency_ratio(m) for level, m in combined.items()},
        experts=len({judgment.expert_id for judgment in judgments}),
    )


def integral(values: dict[str, float | None], weights: Weights | None) -> dict[str, float | None]:
    result: dict[str, float | None] = dict.fromkeys(("QD1", "QD2", "QD3", "Q"))
    if weights is None:
        return result
    for dimension, codes in DIMENSIONS.items():
        if all(values[code] is not None for code in codes):
            result[dimension] = sum(weights.local[code] * values[code] for code in codes)
    if all(result[dimension] is not None for dimension in DIMENSIONS):
        result["Q"] = sum(weights.dimensions[d] * result[d] for d in DIMENSIONS)
    return result
