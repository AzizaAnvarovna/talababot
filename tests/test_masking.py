import pytest

from app.nlp.masking import mask_pii


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("pochtam ali.v@mail.uz", "pochtam [EMAIL]"),
        ("tel +998 90 123-45-67 ga", "tel [TEL] ga"),
        ("901234567 raqam", "[TEL] raqam"),
        ("ID 123456 dir", "ID [ID] dir"),
        ("passport AA1234567", "passport AA[ID]"),
        ("2 kurs 12345 kod", "2 kurs 12345 kod"),
        ("2024-2025 oʻquv yili", "2024-2025 oʻquv yili"),
    ],
)
def test_mask_pii(text, expected):
    assert mask_pii(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ismim Rahmat", "Ismim [ISM]"),
        ("ismim rahmat karimov", "ismim [ISM] [ISM]"),
        ("Men Sardor man", "Men [ISM] man"),
        ("Aziza Karimova yozdi", "[ISM] [ISM] yozdi"),
        ("aziza karimova yozdi", "[ISM] [ISM] yozdi"),
        ("Исмим Азиза", "Исмим [ISM]"),
        ("Азиза Каримова", "[ISM] [ISM]"),
        ("Karimov domla", "[ISM] domla"),
        ("oʻgʻil Ulugʻbek", "oʻgʻil [ISM]"),
    ],
)
def test_names_are_masked(text, expected):
    assert mask_pii(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Rahmat, tushundim",
        "Sinov qachon boʻladi",
        "Toʻlov shartnomasi",
        "To'lov qachon",
        "Tanlov natijasi",
        "Men talaba man",
        "Men Talaba man",
        "sardor bilan gaplashdim",
        "Aziz talabalar",
        "Buxoro davlat universiteti",
        "javob berishingizga umid qilaman",
        "Hammasi ravshan boʻldi",
    ],
)
def test_ordinary_words_are_not_masked(text):
    assert mask_pii(text) == text
