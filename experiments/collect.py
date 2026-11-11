"""Yigʻilgan haqiqiy savollarni shablonning “Murojaatlar” varagʻiga qoʻshadi.

    python -m experiments.collect --from-form data/forma_javoblari.xlsx
    python -m experiments.collect --from-bot

Toifa boʻsh qoldiriladi: uni tadqiqotchi oʻzi belgilaydi,
model taklifi belgilashga taʼsir qilmasligi uchun.
"""

import argparse
import csv
import shutil
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Dialog, Message, User
from app.kb_import import CATEGORIES, normalize_label
from app.nlp.masking import mask_pii
from experiments.make_template import DEFAULT_PATH, REQUESTS_SHEET

SOURCE_HEADER = "Manba"
FORM_QUESTION_HEADER = "savolingiz"
MIN_LENGTH = 5
_HEADER_SCAN_ROWS = 5


class CollectError(ValueError):
    pass


def _lines(text: str) -> list[str]:
    """Bitta javobda bir nechta savol boʻlsa, har bir qator alohida murojaat."""
    return [line.strip(" -•\t") for line in text.splitlines() if len(line.strip()) >= MIN_LENGTH]


def _form_rows(path: Path) -> list[list]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as file:
            return [list(row) for row in csv.reader(file)]
    sheet = load_workbook(path, read_only=True, data_only=True).worksheets[0]
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def _question_column(rows: list[list]) -> tuple[int, int]:
    for header_row, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        labels = [normalize_label(cell) for cell in row]
        for column, label in enumerate(labels):
            if label.startswith(FORM_QUESTION_HEADER):
                return header_row, column
    headers = list(rows[0]) if rows else []
    raise CollectError(f"“Savolingiz” ustuni topilmadi. Ustunlar: {headers}")


def questions_from_form(path: Path) -> list[str]:
    rows = _form_rows(path)
    header_row, column = _question_column(rows)
    questions = []
    for row in rows[header_row + 1 :]:
        value = row[column] if column < len(row) else None
        if value:
            questions.extend(_lines(str(value)))
    return questions


def questions_from_bot(db: Session) -> list[str]:
    """Faqat rozilik bergan talabalar xabarlari; tugma bosishlari va qisqa xabarlar tashlanadi."""
    query = (
        select(Message.text_masked)
        .join(Dialog, Message.dialog_id == Dialog.id)
        .join(User, Dialog.user_id == User.id)
        .where(Message.sender == "talaba", User.consent.is_(True))
        .order_by(Message.id)
    )
    return [
        text
        for text in db.scalars(query)
        if text not in CATEGORIES and len(text.split()) >= 2 and len(text) >= MIN_LENGTH
    ]


def append_to_template(path: Path, questions: list[str], source: str) -> tuple[int, int]:
    if not path.exists():
        raise CollectError(f"Shablon topilmadi: {path}")
    book = load_workbook(path)
    sheet = book[REQUESTS_SHEET]
    if sheet.cell(row=1, column=4).value != SOURCE_HEADER:
        sheet.cell(row=1, column=4, value=SOURCE_HEADER)
        sheet.column_dimensions["D"].width = 12

    existing = {
        normalize_label(row[0]) for row in sheet.iter_rows(min_row=2, values_only=True) if row[0]
    }
    added = skipped = 0
    for question in questions:
        masked = mask_pii(question)
        key = normalize_label(masked)
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        sheet.append([masked, None, None, source])
        added += 1

    shutil.copyfile(path, path.with_suffix(".bak.xlsx"))
    try:
        book.save(path)
    except PermissionError as error:
        raise CollectError("Excel faylni yoping va qayta urinib koʻring.") from error
    return added, skipped


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-form", type=Path, help="Google Forms javoblari (.xlsx yoki .csv)")
    source.add_argument("--from-bot", action="store_true", help="botga yozilgan savollar")
    parser.add_argument("--template", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args(argv)

    try:
        if args.from_bot:
            from app.db.session import SessionLocal

            with SessionLocal() as db:
                questions, label = questions_from_bot(db), "bot"
        else:
            if not args.from_form.exists():
                raise CollectError(f"Fayl topilmadi: {args.from_form}")
            questions, label = questions_from_form(args.from_form), "forma"
        added, skipped = append_to_template(args.template, questions, label)
    except CollectError as error:
        raise SystemExit(str(error)) from error
    print(f"Qoʻshildi: {added} ta savol. Takror boʻlgani uchun oʻtkazildi: {skipped} ta.")
    print("Endi Excel'da “Toifa” va “Imlo xatosi” ustunlarini belgilang.")


if __name__ == "__main__":
    main()
