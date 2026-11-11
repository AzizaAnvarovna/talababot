"""Ishonch chegarasi strategiyasi (FR-10 – FR-13)."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.db.models import KbItem

_MAX_FOLLOW_UP_WORDS = 3
_CLARIFY_OPTIONS = 2
_FOLLOW_UP_PARTICLE = re.compile(r"-chi\b")

Retrieve = Callable[[str, str], tuple[KbItem | None, float]]


@dataclass
class Decision:
    kind: str  # kb | clarify | fallback
    item: KbItem | None = None
    category: str | None = None
    options: list[str] = field(default_factory=list)


def _is_short(query: str) -> bool:
    return len(re.findall(r"\w+", query)) <= _MAX_FOLLOW_UP_WORDS


def decide(
    ranked: list[tuple[str, float]],
    query: str,
    tau: float,
    sigma: float,
    context_category: str | None,
    previous_was_clarify: bool,
    retrieve: Retrieve,
) -> Decision:
    category, confidence = ranked[0]
    understood = confidence >= tau
    if not understood and context_category and _is_short(query):
        category, understood = context_category, True
        query = _FOLLOW_UP_PARTICLE.sub("", query)

    if understood:
        item, similarity = retrieve(query, category)
        if item is not None and similarity >= sigma:
            return Decision("kb", item=item, category=category)

    if previous_was_clarify:
        return Decision("fallback")
    return Decision("clarify", options=[name for name, _ in ranked[:_CLARIFY_OPTIONS]])
