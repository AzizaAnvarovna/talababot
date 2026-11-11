import pytest

from app.nlp import classifier
from app.nlp.classifier import RULE_BASED, SVM, RuleBasedClassifier, get_classifier
from app.nlp.normalizer import normalize
from app.nlp.train_svm import train

TEXTS = {
    "Stipendiya": ["stipendiya qachon", "stipendiya miqdori", "grant puli", "stipendiya kartasi"],
    "Yotoqxona": ["yotoqxona joyi", "yotoqxona narxi", "ttj bormi", "yotoqxonaga kirish"],
}


def training_data():
    return [t for ts in TEXTS.values() for t in ts], [c for c, ts in TEXTS.items() for _ in ts]


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("Stipendiya qachon beriladi", "Stipendiya"),
        ("Стипендия қачон берилади", "Stipendiya"),
        ("Yotoqxonaga joy kerak", "Yotoqxona"),
        ("Dars jadvali qayerda", "Oʻquv jarayoni"),
        ("Maʼlumotnoma olish uchun ariza", "Hujjatlar va arizalar"),
        ("Akademik taʼtil olmoqchiman", "Akademik taʼtil va koʻchirish"),
        ("Kutubxona ishlaydimi", "Boshqa"),
    ],
)
def test_rule_based_categories(text, category):
    ranked = RuleBasedClassifier().predict(normalize(text))
    assert ranked[0][0] == category
    assert ranked[0][1] >= 0.6


def test_rule_based_probabilities_sum_to_one():
    ranked = RuleBasedClassifier().predict("stipendiya yotoqxona")
    assert len(ranked) == 6
    assert sum(score for _, score in ranked) == pytest.approx(1)
    assert ranked[0][1] < 0.6


def test_unknown_text_has_low_confidence():
    assert RuleBasedClassifier().predict("salom")[0][1] < 0.6


def test_unknown_model_raises():
    with pytest.raises(ValueError):
        get_classifier("nope")


def test_svm_unavailable_without_file(monkeypatch, tmp_path):
    monkeypatch.setattr(classifier, "MODEL_PATH", tmp_path / "svm.joblib")
    assert classifier.available_models() == [RULE_BASED]


def test_svm_train_and_predict(monkeypatch, tmp_path):
    path = tmp_path / "svm.joblib"
    monkeypatch.setattr(classifier, "MODEL_PATH", path)
    train(*training_data(), path)
    assert classifier.available_models() == [RULE_BASED, SVM]
    ranked = get_classifier(SVM).predict("yotoqxona joyi bormi")
    assert ranked[0][0] == "Yotoqxona"
    assert isinstance(ranked[0][1], float)
    assert sum(score for _, score in ranked) == pytest.approx(1)


def test_svm_refuses_too_little_data(tmp_path):
    path = tmp_path / "svm.joblib"
    with pytest.raises(ValueError):
        train(["a", "b"], ["Stipendiya", "Yotoqxona"], path)
    assert not path.exists()
