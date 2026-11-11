"""Shaxsiy maʼlumotlarni maskalash (FR-24)."""

import re

from app.nlp.normalizer import canonical_apostrophes, to_latin

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s()\-]{7,}\d(?!\w)")
_LONG_NUMBER = re.compile(r"\d{6,}")
_MIN_PHONE_DIGITS = 9

_WORD = re.compile(r"[^\W\d_]+(?:['`´ʼ’‘][^\W\d_]+)*")
_SURNAME = re.compile(r".{3,}(?:ov|ova|yev|yeva|ovich|ovna|yevich|yevna)$")
# "-ov" bilan tugaydigan oddiy soʻzlar familiya emas.
_NOT_SURNAMES = frozenset({"sinov", "tanlov", "toʻlov", "mashgʻulov", "tayyorlov", "qarov"})
_NAME_CLUES = frozenset({"ismim", "familiyam"})
_NOT_NAMES_AFTER_MEN = frozenset({"talaba", "magistr", "magistrant", "bakalavr", "oʻqituvchi"})
# Oddiy soʻz boʻlgan ismlar (rahmat, aziz, sardor, olim, erkin ...) atayin kiritilmagan:
# ular faqat “ismim …” qolipi orqali maskalanadi.
_NAMES = frozenset("""
    abdulla abdurahmon abbos akmal alisher anvar asad asadbek aziza azizbek bekzod bobur
    dilnoza dilshod dilfuza diyora doniyor elyor farhod farrux feruza firdavs
    gulnoza gulnora gulbahor hasan husan ibrohim ilhom ismoil jahongir jamshid
    jasur javohir kamola kamron laylo lobar mansur maftuna
    mavluda mohira muhammad muhammadali munisa mustafo nargiza nasiba nilufar nodira
    oybek otabek parvina qodir robiya rustam ruxshona sabina sanjar
    sarvar sevara shahlo shahzod sherzod shohruh sitora sobir sultonbek temur tohir
    ulugʻbek umida xurshid yusuf zarina zebo zilola ziyoda
    """.split())


def _replace_phone(match: re.Match[str]) -> str:
    digits = sum(ch.isdigit() for ch in match.group())
    return "[TEL]" if digits >= _MIN_PHONE_DIGITS else match.group()


def _canonical_word(word: str) -> str:
    return canonical_apostrophes(to_latin(word.lower()))


def _looks_like_surname(word: str) -> bool:
    return _SURNAME.match(word) is not None and word not in _NOT_SURNAMES


def _name_positions(words: list[str], capitalized: list[bool]) -> set[int]:
    flagged: set[int] = set()
    for index, word in enumerate(words):
        previous = words[index - 1] if index else ""
        following = words[index + 1] if index + 1 < len(words) else ""
        says_who = (
            previous == "men"
            and following in ("man", "manman")
            and capitalized[index]
            and word not in _NOT_NAMES_AFTER_MEN
        )
        if (
            word in _NAMES
            or previous in _NAME_CLUES
            or says_who
            or (capitalized[index] and _looks_like_surname(word))
        ):
            flagged.add(index)
    # "aziza karimova": kichik harfli familiya ism yonida boʻlsa ham maskalanadi.
    for index, word in enumerate(words):
        if _looks_like_surname(word) and {index - 1, index + 1} & flagged:
            flagged.add(index)
    return flagged


def _mask_names(text: str) -> str:
    matches = list(_WORD.finditer(text))
    words = [_canonical_word(match.group()) for match in matches]
    capitalized = [match.group()[0].isupper() for match in matches]
    for index in sorted(_name_positions(words, capitalized), reverse=True):
        start, end = matches[index].span()
        text = f"{text[:start]}[ISM]{text[end:]}"
    return text


def mask_pii(text: str) -> str:
    text = _EMAIL.sub("[EMAIL]", text)
    text = _PHONE.sub(_replace_phone, text)
    text = _LONG_NUMBER.sub("[ID]", text)
    return _mask_names(text)
