"""Toifa ichidan eng oʻxshash yozuvni tanlash (FR-10, FR-17)."""

from collections.abc import Mapping
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KbItem
from app.nlp.normalizer import normalize


@lru_cache(maxsize=32)
def _fit_index(samples: tuple[str, ...], slang: tuple[tuple[str, str], ...]):
    """Kalit — savollarning matni, shuning uchun bilimlar bazasi oʻzgarsa kesh ishlamay qoladi."""
    # Harf n-gramlari oʻzbekcha qoʻshimchalarga chidamli: "stipendiyam" ~ "stipendiya".
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
    return vectorizer, vectorizer.fit_transform(normalize(s, dict(slang)) for s in samples)


def best_match(
    db: Session, query: str, category: str, slang: Mapping[str, str] | None = None
) -> tuple[KbItem | None, float]:
    items = db.scalars(select(KbItem).where(KbItem.category == category, KbItem.verified.is_(True)))
    pairs = [
        (item, sample) for item in items for sample in item.questions.splitlines() if sample.strip()
    ]
    if not pairs:
        return None, 0.0
    vectorizer, matrix = _fit_index(
        tuple(sample for _, sample in pairs), tuple(sorted((slang or {}).items()))
    )
    similarities = cosine_similarity(vectorizer.transform([query]), matrix)[0]
    best = int(similarities.argmax())
    return pairs[best][0], float(similarities[best])
