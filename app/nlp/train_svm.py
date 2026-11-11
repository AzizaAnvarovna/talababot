"""SVM modelini bilimlar bazasidagi savol namunalarida oʻqitadi: python -m app.nlp.train_svm

Haqiqiy murojaatlar yigʻilgach model experiments.train_baselines --register orqali almashtiriladi.
"""

from pathlib import Path

import joblib
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KbItem
from app.db.session import SessionLocal
from app.nlp import classifier
from app.nlp.normalizer import normalize
from app.nlp.pipelines import build_svm
from app.settings_store import load_slang


def train(texts: list[str], labels: list[str], path: Path) -> None:
    pipeline = build_svm(labels)
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
