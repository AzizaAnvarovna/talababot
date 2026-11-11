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
