import pytest

from app.nlp.normalizer import normalize, to_latin

SLANG = {"stipuxa": "stipendiya", "stipa": "stipendiya", "obshaga": "yotoqxona"}


@pytest.mark.parametrize(
    ("cyrillic", "latin"),
    [
        ("ўқиш жадвали қачон", "oʻqish jadvali qachon"),
        ("ҳужжат", "hujjat"),
        ("ғалаба", "gʻalaba"),
        ("стипендия", "stipendiya"),
        ("ер", "yer"),
        ("келди", "keldi"),
        ("маълумот", "maʻlumot"),
        ("цирк", "sirk"),
        ("акция", "aksiya"),
        ("лицей", "litsey"),
        ("шаҳар", "shahar"),
        ("чой", "choy"),
    ],
)
def test_to_latin(cyrillic, latin):
    assert to_latin(cyrillic) == latin


@pytest.mark.parametrize("variant", ["o'qish", "o`qish", "oʻqish", "o’qish", "o‘qish", "oʼqish"])
def test_apostrophe_variants_become_one(variant):
    assert normalize(variant) == "oʻqish"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("  Salom    DUNYO ", "salom dunyo"),
        ("rahmaaat", "rahmat"),
        ("Ўқиш", "oʻqish"),
        ("'qoʻshtirnoq'", "qoʻshtirnoq"),
        ("kitobbbb", "kitob"),
        ("rahmmat", "rahmmat"),
    ],
)
def test_normalize(text, expected):
    assert normalize(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("stipuxa qachon", "stipendiya qachon"),
        ("stipuxam kelmadi", "stipendiyam kelmadi"),
        ("stipuxalarga", "stipendiyalarga"),
        ("СТИПУХА", "stipendiya"),
        ("stipendiya", "stipendiya"),
        ("obshagada joy", "yotoqxonada joy"),
    ],
)
def test_slang(text, expected):
    assert normalize(text, SLANG) == expected


def test_no_slang_is_noop():
    assert normalize("stipuxa", {}) == "stipuxa"
