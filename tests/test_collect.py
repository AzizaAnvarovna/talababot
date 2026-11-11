import csv

import pytest
from openpyxl import Workbook, load_workbook

from app.db.models import Dialog, Message, User
from experiments.collect import (
    append_to_template,
    main,
    questions_from_bot,
    questions_from_form,
)
from experiments.dataset import load_dataset
from experiments.make_template import REQUESTS_SHEET, build


@pytest.fixture
def template(tmp_path):
    path = tmp_path / "shablon.xlsx"
    build(path)
    return path


def form_xlsx(path, answers, header="Savolingiz (har bir savolni yangi qatordan yozing)"):
    book = Workbook()
    book.active.append(["Vaqt belgisi", header])
    for answer in answers:
        book.active.append(["2026-11-12", answer])
    book.save(path)
    return path


def requests(path):
    sheet = load_workbook(path)[REQUESTS_SHEET]
    return [row for row in sheet.iter_rows(min_row=2, values_only=True)]


def test_form_answers_split_into_lines(tmp_path):
    path = form_xlsx(
        tmp_path / "f.xlsx", ["Stipendiya qachon tushadi?\n- Yotoqxona bormi", "ok", None]
    )
    assert questions_from_form(path) == ["Stipendiya qachon tushadi?", "Yotoqxona bormi"]


def test_form_csv_is_supported(tmp_path):
    path = tmp_path / "f.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        csv.writer(file).writerows([["Vaqt", "Savolingiz"], ["x", "Ётоқхона қачон очилади?"]])
    assert questions_from_form(path) == ["Ётоқхона қачон очилади?"]


def test_form_without_question_column(tmp_path):
    path = form_xlsx(tmp_path / "f.xlsx", ["a"], header="Boshqa ustun")
    with pytest.raises(Exception, match="Savolingiz"):
        questions_from_form(path)


def test_append_masks_dedupes_and_marks_source(template):
    added, skipped = append_to_template(
        template,
        [
            "Stipendiya qachon? tel 901234567",
            "stipendiya  qachon? tel 901234567",
            "Ismim Aziza, ariza",
        ],
        "forma",
    )
    assert (added, skipped) == (2, 1)
    rows = requests(template)
    assert rows[0] == ("Stipendiya qachon? tel [TEL]", None, None, "forma")
    assert "Aziza" not in rows[1][0]
    assert load_workbook(template)[REQUESTS_SHEET]["D1"].value == "Manba"
    assert template.with_suffix(".bak.xlsx").exists()

    assert append_to_template(template, ["Stipendiya qachon? tel 901234567"], "bot") == (0, 1)


def test_appended_rows_wait_for_labels(template):
    append_to_template(template, [f"savol raqam {n} haqida" for n in range(10)], "forma")
    book = load_workbook(template)
    for row in range(2, 12):
        book[REQUESTS_SHEET].cell(row=row, column=2, value="Stipendiya" if row % 2 else "Yotoqxona")
    book.save(template)
    assert len(load_dataset(template).samples) == 10


def add_message(db, text, consent=True):
    user = User(user_hash=f"h{db.query(User).count()}", channel="telegram", consent=consent)
    db.add(user)
    db.flush()
    dialog = Dialog(user_id=user.id, channel="telegram", model_version="rule-based")
    db.add(dialog)
    db.flush()
    db.add(Message(dialog_id=dialog.id, sender="talaba", text_masked=text))
    db.add(Message(dialog_id=dialog.id, sender="bot", text_masked="bot javobi"))
    db.commit()


def test_bot_questions_only_from_consenting_students(db_session):
    add_message(db_session, "Stipendiya qachon tushadi?")
    add_message(db_session, "Yotoqxona narxi qancha?", consent=False)
    add_message(db_session, "Stipendiya")
    add_message(db_session, "rahmat")
    assert questions_from_bot(db_session) == ["Stipendiya qachon tushadi?"]


def test_main_reports_missing_files(tmp_path, template):
    with pytest.raises(SystemExit, match="topilmadi"):
        main(["--from-form", str(tmp_path / "yoq.xlsx"), "--template", str(template)])
    form = form_xlsx(tmp_path / "f.xlsx", ["Diplom qachon beriladi?"])
    with pytest.raises(SystemExit, match="Shablon topilmadi"):
        main(["--from-form", str(form), "--template", str(tmp_path / "yoq.xlsx")])


def test_main_appends_form(tmp_path, template, capsys):
    form = form_xlsx(tmp_path / "f.xlsx", ["Diplom qachon beriladi?"])
    main(["--from-form", str(form), "--template", str(template)])
    assert "Qoʻshildi: 1" in capsys.readouterr().out
    assert requests(template)[0][0] == "Diplom qachon beriladi?"
