import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.db.models import KbItem
from app.kb_import import CATEGORIES, import_workbook
from experiments.dataset import load_dataset
from experiments.make_template import KB_SHEET, REQUESTS_SHEET, build, main


@pytest.fixture
def template(tmp_path):
    path = tmp_path / "shablon.xlsx"
    build(path)
    return path


def fill(path, requests=(), kb=()):
    book = load_workbook(path)
    for row in requests:
        book[REQUESTS_SHEET].append(row)
    for row in kb:
        book[KB_SHEET].append(row)
    book.save(path)


def test_sheets_and_headers(template):
    book = load_workbook(template)
    assert book.sheetnames == ["Qoidalar", "Murojaatlar", "Bilimlar bazasi", "Hisob"]
    assert [c.value for c in book[REQUESTS_SHEET][1]] == ["Murojaat", "Toifa", "Imlo xatosi"]
    assert book[REQUESTS_SHEET].max_row == 1


def test_dropdowns_use_exact_category_names(template):
    validations = load_workbook(template)[REQUESTS_SHEET].data_validations.dataValidation
    lists = {str(v.sqref): v.formula1 for v in validations}
    assert lists["B2:B5001"] == '"' + ",".join(CATEGORIES) + '"'
    assert lists["C2:C5001"] == '"Ha,Yoʻq"'


def test_filled_template_is_read_by_experiment(template):
    rows = []
    for category in CATEGORIES:
        for number in range(6):
            rows.append([f"{category} haqida {number}-savol", category, "Yoʻq"])
    rows.append(["stipuxa qachon tushadi", "Stipendiya", "Ha"])
    fill(template, requests=rows)
    dataset = load_dataset(template)
    assert len(dataset.samples) == len(rows)
    assert sum(sample.typo for sample in dataset.samples) == 1
    assert dataset.skipped_rows == []


def test_filled_template_is_read_by_knowledge_base_import(template, db_session):
    fill(
        template,
        kb=[
            [
                "Stipendiya",
                "stipendiya_muddati",
                "Stipendiya qachon beriladi?; Stipendiya kuni qaysi?",
                "Rasmiy javob",
                "",
                "Buxgalteriya",
                "Ha",
            ]
        ],
    )
    with template.open("rb") as file:
        result = import_workbook(db_session, file)
    assert result.created == 1
    item = db_session.scalars(select(KbItem)).one()
    assert item.questions.splitlines() == ["Stipendiya qachon beriladi?", "Stipendiya kuni qaysi?"]
    assert item.department == "Buxgalteriya"
    assert item.verified is True


def test_count_formulas_reference_both_sheets(template):
    sheet = load_workbook(template)["Hisob"]
    assert sheet["B4"].value == "=COUNTIF(Murojaatlar!$B:$B,$A4)"
    assert sheet["G4"].value == "=COUNTIF('Bilimlar bazasi'!$A:$A,$A4)"
    assert sheet["A10"].value == "Jami"
    assert sheet["B10"].value == "=SUM(B4:B9)"


def test_existing_file_is_not_overwritten(template):
    template.write_bytes(b"to'ldirilgan")
    with pytest.raises(SystemExit, match="ustidan yozilmadi"):
        main(["--out", str(template)])
    assert template.read_bytes() == b"to'ldirilgan"
