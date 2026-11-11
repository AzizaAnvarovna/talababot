import pytest

from app.nlp.normalizer import normalize
from app.nlp.sentiment import score


@pytest.mark.parametrize("text", ["stipendiya qachon", "salom", ""])
def test_neutral(text):
    assert score(normalize(text)) == 0.0


def test_positive_and_negative_signs():
    assert score("rahmat yaxshi") > 0.5
    assert score("yomon") < -0.25
    assert score("notoʻgʻri javob") < -0.25


def test_negation_flips():
    assert score("yaxshi emas") < 0
    assert score("yomon emas") > 0


def test_intensifier_strengthens():
    assert score("juda yomon") < score("yomon")


def test_mixed_is_between():
    assert score("yaxshi lekin yomon") == 0


def test_always_in_range():
    text = " ".join(["juda yomon"] * 20)
    assert -1 <= score(text) <= 1
    assert -1 <= score(" ".join(["juda yaxshi"] * 20)) <= 1


def test_works_after_normalization():
    assert score(normalize("Ёмон, нотўғри")) < -0.25
