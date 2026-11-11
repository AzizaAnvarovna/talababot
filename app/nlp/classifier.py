"""Murojaatni toifalash (FR-9, FR-14). Matn normallashgan holda keladi."""

import re
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path
from typing import Protocol

import joblib

from app.kb_import import CATEGORIES

RULE_BASED = "rule-based"
SVM = "svm"
TRANSFORMER = "transformer"
MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "svm.joblib"
TRANSFORMER_PATH = Path(__file__).resolve().parents[2] / "models" / "transformer"
_TRANSFORMER_MAX_LENGTH = 128

Ranked = list[tuple[str, float]]

# Har bir soʻz shu bilan boshlansa toifaga bir ball beriladi.
KEYWORDS = {
    "Oʻquv jarayoni": (
        "dars",
        "imtihon",
        "jadval",
        "sessiya",
        "baho",
        "fan",
        "kredit",
        "reyting",
        "oʻqituvchi",
        "kurs",
        "semestr",
        "qayta topshir",
    ),
    "Stipendiya": ("stipendiya", "grant", "nafaqa", "plastik", "karta"),
    "Yotoqxona": ("yotoq", "ttj", "ijara", "xona"),
    "Hujjatlar va arizalar": (
        "hujjat",
        "ariza",
        "maʻlumotnoma",
        "diplom",
        "transkript",
        "guvohnoma",
        "nusxa",
        "shartnoma",
        "kontrakt",
    ),
    "Akademik taʼtil va koʻchirish": (
        "akademik",
        "taʻtil",
        "koʻchir",
        "oʻtkazish",
        "tikla",
        "chetlat",
    ),
    "Boshqa": ("kutubxona", "sport", "oshxona", "wifi", "internet", "tadbir"),
}
_SMOOTHING = 0.1


class Classifier(Protocol):
    def predict(self, text: str) -> Ranked:
        """Toifalarni ehtimollik boʻyicha kamayish tartibida qaytaradi."""


class RuleBasedClassifier:
    def predict(self, text: str) -> Ranked:
        tokens = re.findall(r"\w+", text)
        hits = {
            category: sum(token.startswith(words) for token in tokens)
            for category, words in KEYWORDS.items()
        }
        total = sum(hits.values()) + _SMOOTHING * len(CATEGORIES)
        scores = [(c, (hits[c] + _SMOOTHING) / total) for c in CATEGORIES]
        return sorted(scores, key=lambda pair: -pair[1])


class SvmClassifier:
    def __init__(self, pipeline) -> None:
        self._pipeline = pipeline

    def predict(self, text: str) -> Ranked:
        probabilities = self._pipeline.predict_proba([text])[0]
        pairs = zip(self._pipeline.classes_, probabilities, strict=True)
        return sorted(((str(c), float(p)) for c, p in pairs), key=lambda pair: -pair[1])


@lru_cache(maxsize=4)
def _load_pipeline(path: Path, _modified: float):
    return joblib.load(path)


class TransformerClassifier:
    def __init__(self, model, tokenizer) -> None:
        self._model = model
        self._tokenizer = tokenizer

    def predict(self, text: str) -> Ranked:
        import torch

        inputs = self._tokenizer(
            text, truncation=True, max_length=_TRANSFORMER_MAX_LENGTH, return_tensors="pt"
        )
        with torch.no_grad():
            logits = self._model(**inputs).logits[0]
        labels = self._model.config.id2label
        scores = [(labels[i], float(p)) for i, p in enumerate(torch.softmax(logits, -1))]
        return sorted(scores, key=lambda pair: -pair[1])


@lru_cache(maxsize=2)
def _load_transformer(path: Path, _modified: float) -> TransformerClassifier:
    # Ogʻir kutubxonalar faqat shu model tanlanganda yuklanadi.
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    model = AutoModelForSequenceClassification.from_pretrained(path).eval()
    return TransformerClassifier(model, AutoTokenizer.from_pretrained(path))


def _transformer_ready() -> bool:
    return (TRANSFORMER_PATH / "config.json").exists() and all(
        find_spec(name) is not None for name in ("torch", "transformers")
    )


def available_models() -> list[str]:
    models = [RULE_BASED]
    if MODEL_PATH.exists():
        models.append(SVM)
    if _transformer_ready():
        models.append(TRANSFORMER)
    return models


def get_classifier(name: str) -> Classifier:
    if name == RULE_BASED:
        return RuleBasedClassifier()
    if name == SVM:
        return SvmClassifier(_load_pipeline(MODEL_PATH, MODEL_PATH.stat().st_mtime))
    if name == TRANSFORMER:
        config = TRANSFORMER_PATH / "config.json"
        return _load_transformer(TRANSFORMER_PATH, config.stat().st_mtime)
    raise ValueError(f"Nomaʼlum model: {name}")
