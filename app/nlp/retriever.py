"""1-bosqich uchun vaqtinchalik qidiruv; 2-bosqichda TF-IDF bilan almashtiriladi (FR-10)."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KbItem

_MIN_SIMILARITY = 0.5


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def find_verified_answer(db: Session, question: str) -> KbItem | None:
    query_tokens = _tokens(question)
    best, best_score = None, 0.0
    for item in db.scalars(select(KbItem).where(KbItem.verified.is_(True))):
        for sample in item.questions.splitlines():
            sample_tokens = _tokens(sample)
            union = query_tokens | sample_tokens
            score = len(query_tokens & sample_tokens) / len(union) if union else 0.0
            if score > best_score:
                best, best_score = item, score
    return best if best_score >= _MIN_SIMILARITY else None
