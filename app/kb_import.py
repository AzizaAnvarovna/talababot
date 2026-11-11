"""Bilimlar bazasini Excel shablonidan import qilish (FR-16)."""

from dataclasses import dataclass, field
from typing import BinaryIO

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KbItem

SHEET_NAME = "Bilimlar bazasi"
CATEGORIES = [
    "Oʻquv jarayoni",
    "Stipendiya",
    "Yotoqxona",
    "Hujjatlar va arizalar",
    "Akademik taʼtil va koʻchirish",
    "Boshqa",
]
_HEADER_SCAN_ROWS = 10
_TRUE_VALUES = {"ha", "yes", "true", "1", "+"}


def normalize_label(value: object) -> str:
    text = "" if value is None else str(value)
    for apostrophe in "`ʻʼ’‘":
        text = text.replace(apostrophe, "'")
    return " ".join(text.lower().split())


_CATEGORY_BY_LABEL = {normalize_label(name): name for name in CATEGORIES}

_COLUMN_ALIASES = {
    "category": {"toifa", "kategoriya"},
    "intent": {"kichik mavzu", "kichik mavzu (intent)", "intent", "mavzu"},
    "questions": {"savol namunalari", "savollar", "savol", "savol namunasi"},
    "answer": {"rasmiy javob", "javob"},
    "source": {"havola yoki hujjat", "havola", "manba", "hujjat"},
    "department": {"mas'ul bo'lim", "bo'lim"},
    "verified": {"tekshirildi", "tasdiqlangan"},
}
_REQUIRED_COLUMNS = ("category", "intent", "questions", "answer")


class KbImportError(ValueError):
    pass


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped_rows: list[int] = field(default_factory=list)


def _match_columns(row: tuple) -> dict[str, int]:
    columns: dict[str, int] = {}
    for index, cell in enumerate(row):
        label = normalize_label(cell)
        for name, aliases in _COLUMN_ALIASES.items():
            if label in aliases and name not in columns:
                columns[name] = index
    return columns


def _find_header(rows: list[tuple]) -> tuple[int, dict[str, int]]:
    for index, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        columns = _match_columns(row)
        if all(name in columns for name in _REQUIRED_COLUMNS):
            return index, columns
    raise KbImportError(
        "Sarlavha qatori topilmadi: toifa, kichik mavzu, savol namunalari, "
        "rasmiy javob ustunlari boʻlishi kerak."
    )


def _cell(row: tuple, columns: dict[str, int], name: str) -> str:
    index = columns.get(name)
    value = row[index] if index is not None and index < len(row) else None
    return "" if value is None else str(value).strip()


def _split_questions(raw: str) -> list[str]:
    parts = raw.replace(";", "\n").splitlines()
    return [part.strip() for part in parts if part.strip()]


def _merge_questions(existing: str, new: list[str]) -> str:
    merged = existing.splitlines()
    merged.extend(question for question in new if question not in merged)
    return "\n".join(merged)


def import_workbook(db: Session, file: BinaryIO) -> ImportResult:
    try:
        workbook = load_workbook(file, read_only=True, data_only=True)
    except Exception as error:  # openpyxl buzuq fayl uchun turli xatolar chiqaradi
        raise KbImportError("Fayl .xlsx formatida oʻqilmadi.") from error
    if SHEET_NAME not in workbook.sheetnames:
        raise KbImportError(f"“{SHEET_NAME}” varagʻi topilmadi.")

    rows = list(workbook[SHEET_NAME].iter_rows(values_only=True))
    header_index, columns = _find_header(rows)

    result = ImportResult()
    known = {(i.category, i.intent, i.answer): i for i in db.scalars(select(KbItem))}
    new_keys = set()

    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        values = {name: _cell(row, columns, name) for name in _COLUMN_ALIASES}
        if not any(values.values()):
            continue
        category = _CATEGORY_BY_LABEL.get(normalize_label(values["category"]))
        questions = _split_questions(values["questions"])
        if not (category and values["intent"] and questions and values["answer"]):
            result.skipped_rows.append(offset)
            continue

        key = (category, values["intent"], values["answer"])
        item = known.get(key)
        if item is None:
            item = KbItem(category=category, intent=values["intent"], answer=values["answer"])
            item.questions = ""
            db.add(item)
            known[key] = item
            new_keys.add(key)
            result.created += 1
        elif key not in new_keys:
            result.updated += 1
        item.questions = _merge_questions(item.questions, questions)
        item.source = values["source"] or None
        item.department = values["department"] or None
        item.verified = normalize_label(values["verified"]) in _TRUE_VALUES

    db.commit()
    return result
