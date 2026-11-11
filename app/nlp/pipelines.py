"""Klassik modellar konveyerlari: ilova ham, eksperiment ham shularni ishlatadi."""

from collections import Counter

from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import StratifiedKFold
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.svm import LinearSVC

SEED = 42
MAX_FOLDS = 5
MIN_SAMPLES_PER_CATEGORY = 3


def _vectorizer() -> TfidfVectorizer:
    # lowercase=False: normallashtirishsiz tajribada matnga hech narsa tegmasligi kerak.
    return TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, lowercase=False
    )


def build_svm(labels: list[str]) -> Pipeline:
    counts = Counter(labels)
    if len(counts) < 2 or min(counts.values()) < MIN_SAMPLES_PER_CATEGORY:
        raise ValueError(
            f"Kamida 2 ta toifa va har birida {MIN_SAMPLES_PER_CATEGORY} ta namuna kerak: "
            f"{dict(counts)}"
        )
    folds = StratifiedKFold(
        n_splits=min(MAX_FOLDS, min(counts.values())), shuffle=True, random_state=SEED
    )
    return make_pipeline(
        _vectorizer(),
        CalibratedClassifierCV(LinearSVC(class_weight="balanced", random_state=SEED), cv=folds),
    )


def build_naive_bayes() -> Pipeline:
    return make_pipeline(_vectorizer(), MultinomialNB())
