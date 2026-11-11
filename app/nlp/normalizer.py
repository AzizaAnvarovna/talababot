"""Matnni normallashtirish (FR-5, FR-6, FR-7)."""

import re
from collections.abc import Mapping
from functools import lru_cache

APOSTROPHE = "ʻ"
_APOSTROPHES = str.maketrans(dict.fromkeys("'`´ʼ’‘", APOSTROPHE))
_CYRILLIC_VOWELS = "аеёиоуэюяў"
_CYRILLIC_CONSONANTS = "бвгджзйклмнпрстфхцчшщқғҳ"
_CYRILLIC_MAP = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "ё": "yo",
    "ж": "j",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "x",
    "ч": "ch",
    "ш": "sh",
    "щ": "sh",
    "ъ": APOSTROPHE,
    "ы": "i",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "ў": "oʻ",
    "қ": "q",
    "ғ": "gʻ",
    "ҳ": "h",
}
_LETTER = r"[^\W\d_]"
_STRAY_APOSTROPHE = re.compile(rf"(?<!{_LETTER}){APOSTROPHE}|{APOSTROPHE}(?!{_LETTER})")
_REPEATED_LETTER = re.compile(rf"({_LETTER})\1{{2,}}")
# Oʻzbekcha qoʻshimchalar: "stipuxam", "stipuxani", "stipuxalarga" ham lugʻatga tushishi uchun.
_SUFFIXES = r"(?:lar)?(?:imiz|ingiz|im|ing|si|m|ng|i)?(?:ning|dan|ni|ga|ka|qa|da)?"


def _to_latin_char(char: str, previous: str) -> str:
    if char == "е":
        after_consonant = previous in _CYRILLIC_CONSONANTS and previous != ""
        return "e" if after_consonant else "ye"
    if char == "ц":
        return "ts" if previous and previous in _CYRILLIC_VOWELS else "s"
    return _CYRILLIC_MAP.get(char, char)


def to_latin(text: str) -> str:
    """Kichik harfli kirill matnni lotinga oʻgiradi; boshqa belgilar oʻzgarmaydi."""
    return "".join(
        _to_latin_char(char, text[index - 1] if index else "") for index, char in enumerate(text)
    )


def canonical_apostrophes(text: str) -> str:
    return text.translate(_APOSTROPHES)


@lru_cache(maxsize=8)
def _compile_slang(items: tuple[tuple[str, str], ...]) -> re.Pattern[str]:
    terms = "|".join(re.escape(term) for term, _ in sorted(items, key=lambda i: -len(i[0])))
    return re.compile(rf"(?<!\w)({terms})({_SUFFIXES})(?!\w)")


def _apply_slang(text: str, slang: Mapping[str, str]) -> str:
    if not slang:
        return text
    pattern = _compile_slang(tuple(sorted(slang.items())))
    return pattern.sub(lambda match: slang[match.group(1)] + match.group(2), text)


def normalize(text: str, slang: Mapping[str, str] | None = None) -> str:
    text = canonical_apostrophes(to_latin(text.lower()))
    text = _STRAY_APOSTROPHE.sub("", text)
    text = _REPEATED_LETTER.sub(r"\1", text)
    text = " ".join(text.split())
    return _apply_slang(text, slang or {})
