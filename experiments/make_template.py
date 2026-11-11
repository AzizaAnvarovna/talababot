"""Maʼlumot yigʻish uchun Excel shablon: python -m experiments.make_template

Ustunlar experiments.dataset va app.kb_import aynan oʻqiydigan nomlarda.
"""

import argparse
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from app.kb_import import CATEGORIES
from app.kb_import import SHEET_NAME as KB_SHEET

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "Murojaatlar_yigish_shabloni.xlsx"
REQUESTS_SHEET = "Murojaatlar"
RULES_SHEET = "Qoidalar"
COUNT_SHEET = "Hisob"
TARGET_PER_CATEGORY = 150
INPUT_ROWS = 5000
YES, NO = "Ha", "Yoʻq"

FONT = "Arial"
_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
_TOTAL_FILL = PatternFill("solid", fgColor="D9E1F2")

REQUEST_COLUMNS = (("Murojaat", 80), ("Toifa", 32), ("Imlo xatosi", 14))
KB_COLUMNS = (
    ("Toifa", 30),
    ("Kichik mavzu", 22),
    ("Savol namunalari", 50),
    ("Rasmiy javob", 60),
    ("Havola yoki hujjat", 30),
    ("Masʼul boʻlim", 22),
    ("Tekshirildi", 13),
)

RULES = (
    ("TalabaBot: maʼlumot yigʻish shabloni", "title"),
    ("", None),
    ("Qaysi kataklarni toʻldirasiz", "heading"),
    ("• “Murojaatlar” varagʻi: har bir qatorda bitta talaba murojaati.", None),
    ("• “Bilimlar bazasi” varagʻi: har bir qatorda bitta rasmiy javob.", None),
    ("• “Hisob” varagʻini oʻzgartirmang: u yigʻilgan sonlarni oʻzi hisoblaydi.", None),
    (
        "• Sarlavha qatorlari va varaq nomlarini oʻzgartirmang, "
        "aks holda dastur faylni oʻqiy olmaydi.",
        None,
    ),
    ("", None),
    ("“Murojaatlar” varagʻi", "heading"),
    (
        "Murojaat — talaba qanday yozgan boʻlsa, shunday: "
        "kirill yoki lotin, xatolari bilan. Tuzatmang.",
        None,
    ),
    ("Toifa — roʻyxatdan tanlang (6 ta toifa).", None),
    ("Imlo xatosi — matnda imlo xatosi boʻlsa “Ha”, boʻlmasa “Yoʻq”.", None),
    ("Har toifada kamida 150 ta murojaat kerak (TZ, 11-boʻlim).", None),
    ("Bir xil matnni qayta yozmang: dastur takrorlarni baribir olib tashlaydi.", None),
    (
        "Ism, telefon, email va pasport raqamini yozmang; "
        "dastur ularni yashiradi, lekin yozmagan maʼqul.",
        None,
    ),
    ("", None),
    ("Namuna:", "heading"),
    ("Murojaat: “stipuxa qachon tushadi”   Toifa: Stipendiya   Imlo xatosi: Ha", None),
    ("Murojaat: “Ётоқхонага қандай жойлашаман?”   Toifa: Yotoqxona   Imlo xatosi: Yoʻq", None),
    ("", None),
    ("“Bilimlar bazasi” varagʻi", "heading"),
    ("Toifa — roʻyxatdan tanlang.", None),
    ("Kichik mavzu — qisqa nom, masalan: stipendiya_muddati.", None),
    ("Savol namunalari — shu javobga mos 2–5 ta savol, har biri “;” bilan ajratiladi.", None),
    ("Rasmiy javob — dekanat yoki masʼul boʻlim tasdiqlagan matn.", None),
    (
        "Havola yoki hujjat, Masʼul boʻlim — javob manbasi; talabaga javob ostida koʻrsatiladi.",
        None,
    ),
    ("Tekshirildi — faqat “Ha” boʻlgan javoblar talabaga koʻrsatiladi.", None),
    ("", None),
    ("Namuna:", "heading"),
    (
        "Toifa: Stipendiya   Kichik mavzu: stipendiya_muddati   "
        "Savol namunalari: Stipendiya qachon beriladi?; Stipendiya kuni qaysi?   "
        "Rasmiy javob: (dekanat tasdiqlagan javob)   Masʼul boʻlim: Buxgalteriya   Tekshirildi: Ha",
        None,
    ),
    ("", None),
    ("Toʻldirilgan faylni shu nom bilan data papkasida saqlang.", "heading"),
)


def _style_header(sheet, columns) -> None:
    for index, (title, width) in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=index, value=title)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.column_dimensions[cell.column_letter].width = width
    sheet.row_dimensions[1].height = 22
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{sheet.cell(row=1, column=len(columns)).column_letter}1"


def _list_validation(values: list[str], title: str) -> DataValidation:
    validation = DataValidation(
        type="list",
        formula1='"' + ",".join(values) + '"',
        allow_blank=True,
        showErrorMessage=True,
        errorTitle=title,
        error="Roʻyxatdan tanlang.",
    )
    return validation


def _input_sheet(book: Workbook, title: str, columns, list_columns: dict[str, list[str]]):
    sheet = book.create_sheet(title)
    _style_header(sheet, columns)
    last_row = INPUT_ROWS + 1
    for index, (name, _) in enumerate(columns, start=1):
        letter = sheet.cell(row=1, column=index).column_letter
        if name in list_columns:
            validation = _list_validation(list_columns[name], name)
            sheet.add_data_validation(validation)
            validation.add(f"{letter}2:{letter}{last_row}")
    return sheet


def _rules_sheet(sheet) -> None:
    sheet.title = RULES_SHEET
    sheet.column_dimensions["A"].width = 120
    for number, (text, kind) in enumerate(RULES, start=1):
        cell = sheet.cell(row=number, column=1, value=text)
        size = 14 if kind == "title" else 10
        cell.font = Font(name=FONT, bold=kind is not None, size=size)
        cell.alignment = Alignment(wrap_text=True, vertical="top")


def _count_sheet(book: Workbook) -> None:
    sheet = book.create_sheet(COUNT_SHEET)
    sheet["A1"] = "Har toifa uchun maqsad (TZ, 11-boʻlim):"
    sheet["A1"].font = Font(name=FONT, bold=True)
    sheet["B1"] = TARGET_PER_CATEGORY
    sheet["B1"].font = Font(name=FONT, color="0000FF", bold=True)
    sheet["B1"].fill = _INPUT_FILL

    headers = (
        "Toifa",
        "Murojaatlar",
        "Imlo xatoli",
        "Maqsad",
        "Yetishmaydi",
        "Holat",
        "Bilimlar bazasi",
        "Tekshirilgan javoblar",
    )
    for index, title in enumerate(headers, start=1):
        cell = sheet.cell(row=3, column=index, value=title)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    widths = (32, 14, 13, 10, 13, 14, 16, 20)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[sheet.cell(row=3, column=index).column_letter].width = width

    requests, kb = f"{REQUESTS_SHEET}!", f"'{KB_SHEET}'!"
    first = 4
    for offset, category in enumerate(CATEGORIES):
        row = first + offset
        values = (
            category,
            f"=COUNTIF({requests}$B:$B,$A{row})",
            f'=COUNTIFS({requests}$B:$B,$A{row},{requests}$C:$C,"{YES}")',
            "=$B$1",
            f"=MAX(0,D{row}-B{row})",
            f'=IF(E{row}=0,"Yetarli","Kam")',
            f"=COUNTIF({kb}$A:$A,$A{row})",
            f'=COUNTIFS({kb}$A:$A,$A{row},{kb}$G:$G,"{YES}")',
        )
        for column, value in enumerate(values, start=1):
            sheet.cell(row=row, column=column, value=value).font = Font(name=FONT)

    total = first + len(CATEGORIES)
    last = total - 1
    sheet.cell(row=total, column=1, value="Jami")
    for column in "BCDEGH":
        sheet[f"{column}{total}"] = f"=SUM({column}{first}:{column}{last})"
    for column in range(1, len(headers) + 1):
        cell = sheet.cell(row=total, column=column)
        cell.font = Font(name=FONT, bold=True)
        cell.fill = _TOTAL_FILL
    sheet.cell(
        row=total + 2, column=1, value="Bu varaq avtomatik hisoblanadi, oʻzgartirmang."
    ).font = Font(name=FONT, italic=True, color="666666")
    sheet.freeze_panes = "A4"


def build(path: Path) -> None:
    book = Workbook()
    # Boʻsh qatorlarni bezamaslik uchun shrift butun kitobga beriladi.
    book._named_styles["Normal"].font = Font(name=FONT, size=10)
    _rules_sheet(book.active)
    _input_sheet(
        book,
        REQUESTS_SHEET,
        REQUEST_COLUMNS,
        {"Toifa": list(CATEGORIES), "Imlo xatosi": [YES, NO]},
    )
    _input_sheet(book, KB_SHEET, KB_COLUMNS, {"Toifa": list(CATEGORIES), "Tekshirildi": [YES, NO]})
    _count_sheet(book)
    book.active = 1
    book.calculation.fullCalcOnLoad = True
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--force", action="store_true", help="mavjud faylni ustidan yozish")
    args = parser.parse_args(argv)
    if args.out.exists() and not args.force:
        raise SystemExit(f"Fayl allaqachon bor, ustidan yozilmadi: {args.out}")
    build(args.out)
    print(f"Shablon tayyor: {args.out}")


if __name__ == "__main__":
    main()
