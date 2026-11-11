"""Toifa ichidan eng oʻxshash yozuvni tanlash (FR-10, FR-17)."""

from collections.abc import Mapping

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KbItem
from app.nlp.normalizer import normalize


def best_match(
    db: Session, query: str, category: str, slang: Mapping[str, str] | None = None
) -> tuple[KbItem | None, float]:
    items = db.scalars(select(KbItem).where(KbItem.category == category, KbItem.verified.is_(True)))
    pairs = [
        (item, normalize(sample, slang))
        for item in items
        for sample in item.questions.splitlines()
        if sample.strip()
    ]
    if not pairs:
        return None, 0.0
    # Harf n-gramlari oʻzbekcha qoʻshimchalarga chidamli: "stipendiyam" ~ "stipendiya".
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
    matrix = vectorizer.fit_transform(sample for _, sample in pairs)
    similarities = cosine_similarity(vectorizer.transform([query]), matrix)[0]
    best = int(similarities.argmax())
    return pairs[best][0], float(similarities[best])
