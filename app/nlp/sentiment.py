"""Lugʻat va qoidalarga asoslangan hissiy baho, s ∈ [-1; 1] (FR-20). Matn normallashgan keladi."""

import re

_POSITIVE = (
    "rahmat",
    "raxmat",
    "tashakkur",
    "yaxshi",
    "ajoyib",
    "zoʻr",
    "qoyil",
    "foydali",
    "tushunarli",
    "mamnun",
    "xursand",
)
_NEGATIVE = (
    "yomon",
    "xato",
    "notoʻgʻri",
    "tushunmadim",
    "tushunarsiz",
    "qoniqarsiz",
    "foydasiz",
    "ahmoq",
    "afsus",
    "charchadim",
    "jahl",
    "gʻazab",
    "bezdim",
    "adolatsiz",
    "muammo",
    "shikoyat",
)
_INTENSIFIERS = frozenset({"juda", "judayam", "koʻp", "kop"})
_NEGATOR = "emas"
_INTENSIFIER_WEIGHT = 1.5


def score(text: str) -> float:
    tokens = re.findall(r"\w+", text)
    total, hits = 0.0, 0
    for index, token in enumerate(tokens):
        polarity = 1 if token.startswith(_POSITIVE) else -1 if token.startswith(_NEGATIVE) else 0
        if polarity == 0:
            continue
        if index + 1 < len(tokens) and tokens[index + 1] == _NEGATOR:
            polarity = -polarity
        weight = _INTENSIFIER_WEIGHT if index and tokens[index - 1] in _INTENSIFIERS else 1.0
        total += polarity * weight
        hits += 1
    return max(-1.0, min(1.0, total / (hits + 1))) if hits else 0.0
