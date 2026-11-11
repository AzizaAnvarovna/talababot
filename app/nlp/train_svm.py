"""SVM modelini bilimlar bazasidagi savol namunalarida oʻqitadi: python -m app.nlp.train_svm"""

from collections import Counter
from pathlib import Path

import joblib
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.svm import LinearSVC
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KbItem
from app.db.session import SessionLocal
from app.nlp import classifier
from app.nlp.normalizer import normalize
from app.settings_store import load_slang

SEED = 42
MAX_FOLDS = 5
MIN_SAMPLES_PER_CATEGORY = 3


def train(texts: list[str], labels: list[str], path: Path) -> None:
    counts = Counter(labels)
    if len(counts) < 2 or min(counts.values()) < MIN_SAMPLES_PER_CATEGORY:
        raise ValueError(
            f"Kamida 2 ta toifa va har birida {MIN_SAMPLES_PER_CATEGORY} ta namuna kerak: "
            f"{dict(counts)}"
        )
    folds = StratifiedKFold(
        n_splits=min(MAX_FOLDS, min(counts.values())), shuffle=True, random_state=SEED
    )
    pipeline = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True),
        CalibratedClassifierCV(LinearSVC(class_weight="balanced", random_state=SEED), cv=folds),
    )
    pipeline.fit(texts, labels)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, path)


def samples_from_kb(db: Session) -> tuple[list[str], list[str]]:
    slang = load_slang(db)
    texts, labels = [], []
    for item in db.scalars(select(KbItem)):
        for sample in item.questions.splitlines():
            if sample.strip():
                texts.append(normalize(sample, slang))
                labels.append(item.category)
    return texts, labels


def main() -> None:
    with SessionLocal() as db:
        texts, labels = samples_from_kb(db)
    train(texts, labels, classifier.MODEL_PATH)
    print(f"Model saqlandi: {classifier.MODEL_PATH} ({len(texts)} ta namuna)")


if __name__ == "__main__":
    main()
