import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s()\-]{7,}\d(?!\w)")
_LONG_NUMBER = re.compile(r"\d{6,}")
_MIN_PHONE_DIGITS = 9


def _replace_phone(match: re.Match[str]) -> str:
    digits = sum(ch.isdigit() for ch in match.group())
    return "[TEL]" if digits >= _MIN_PHONE_DIGITS else match.group()


def mask_pii(text: str) -> str:
    """FR-24: ismlarni maskalash 2-bosqichda qo'shiladi."""
    text = _EMAIL.sub("[EMAIL]", text)
    text = _PHONE.sub(_replace_phone, text)
    return _LONG_NUMBER.sub("[ID]", text)
