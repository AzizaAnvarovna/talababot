from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.auth import create_or_update_staff
from app.db.models import KbItem

HEADERS = [
    "Toifa",
    "Kichik mavzu",
    "Savol namunalari",
    "Rasmiy javob",
    "Havola",
    "Mas’ul bo‘lim",
    "Tekshirildi",
]
FORM = {
    "category": "Stipendiya",
    "intent": "muddat",
    "questions": " Qachon?\n\nQaysi kuni? ",
    "answer": "25-sanada.",
    "source": "",
    "department": "Buxgalteriya",
    "verified": "on",
}


def workbook(rows, sheet="Bilimlar bazasi", title=False):
    book = Workbook()
    ws = book.active
    ws.title = sheet
    if title:
        ws.append(["Bilimlar bazasi shabloni"])
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def upload(client, content):
    name = "kb.xlsx"
    return client.post("/admin/kb/import", files={"file": (name, content)})


def items(db):
    db.expire_all()
    return db.scalars(select(KbItem)).all()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin"),
        ("get", "/admin/kb"),
        ("get", "/admin/kb/new"),
        ("post", "/admin/kb/new"),
        ("post", "/admin/kb/1/delete"),
        ("post", "/admin/kb/import"),
    ],
)
def test_admin_requires_login(client, method, path):
    response = getattr(client, method)(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_wrong_password_is_rejected(client, db_session):
    create_or_update_staff(db_session, "admin", "correct-password", "admin")
    response = client.post(
        "/admin/login", data={"login": "admin", "password": "no"}, follow_redirects=False
    )
    assert response.status_code == 401
    assert client.get("/admin/kb", follow_redirects=False).status_code == 303


def test_non_ascii_password_does_not_crash(client):
    response = client.post(
        "/admin/login", data={"login": "oʻ", "password": "oʻ"}, follow_redirects=False
    )
    assert response.status_code == 401


def test_logout_ends_session(admin_client):
    admin_client.post("/admin/logout", follow_redirects=False)
    assert admin_client.get("/admin/kb", follow_redirects=False).status_code == 303


def test_create_edit_delete(admin_client, db_session):
    assert admin_client.post("/admin/kb/new", data=FORM, follow_redirects=False).status_code == 303
    item = items(db_session)[0]
    assert item.questions == "Qachon?\nQaysi kuni?"
    assert item.source is None
    assert item.verified is True
    assert "25-sanada." in admin_client.get("/admin/kb").text

    assert admin_client.get(f"/admin/kb/{item.id}/edit").status_code == 200
    changed = {k: v for k, v in FORM.items() if k != "verified"} | {"answer": "26-sanada."}
    admin_client.post(f"/admin/kb/{item.id}/edit", data=changed)
    item = items(db_session)[0]
    assert item.answer == "26-sanada."
    assert item.verified is False

    admin_client.post(f"/admin/kb/{item.id}/delete")
    assert items(db_session) == []


def test_invalid_form_is_not_saved(admin_client, db_session):
    response = admin_client.post("/admin/kb/new", data=FORM | {"category": "Xato"})
    assert response.status_code == 400
    assert items(db_session) == []


def test_missing_item_returns_404(admin_client):
    assert admin_client.get("/admin/kb/999/edit").status_code == 404


ROW = ["stipendiya", "muddat", "Qachon?; Qaysi kuni?", "25-sanada.", "havola", "Buxgalteriya", "Ha"]


def test_import_creates_item_with_canonical_category(admin_client, db_session):
    upload(admin_client, workbook([ROW]))
    item = items(db_session)[0]
    assert item.category == "Stipendiya"
    assert item.questions == "Qachon?\nQaysi kuni?"
    assert item.department == "Buxgalteriya"
    assert item.verified is True


def test_import_finds_header_below_title(admin_client, db_session):
    upload(admin_client, workbook([ROW], title=True))
    assert len(items(db_session)) == 1


def test_import_apostrophe_variant_in_category(admin_client, db_session):
    upload(admin_client, workbook([["O'quv jarayoni", "dars", "Dars?", "Javob", "", "", "Yo'q"]]))
    item = items(db_session)[0]
    assert item.category == "Oʻquv jarayoni"
    assert item.verified is False


def test_reimport_is_idempotent(admin_client, db_session):
    content = workbook([ROW])
    upload(admin_client, content)
    upload(admin_client, content)
    stored = items(db_session)
    assert len(stored) == 1
    assert stored[0].questions == "Qachon?\nQaysi kuni?"


def test_rows_with_same_answer_merge_questions(admin_client, db_session):
    other = ROW[:2] + ["Boshqa savol?"] + ROW[3:]
    upload(admin_client, workbook([ROW, other]))
    stored = items(db_session)
    assert len(stored) == 1
    assert stored[0].questions.splitlines()[-1] == "Boshqa savol?"


def test_bad_rows_are_reported_with_row_number(admin_client, db_session):
    response = upload(admin_client, workbook([ROW, ["Notoʻgʻri", "x", "y", "z", "", "", "Ha"]]))
    assert len(items(db_session)) == 1
    assert "qatorlar: 3" in response.text


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"not an excel file", "oʻqilmadi"),
        (workbook([ROW], sheet="Boshqa varaq"), "varagʻi topilmadi"),
    ],
)
def test_bad_files_show_error(admin_client, db_session, content, message):
    response = upload(admin_client, content)
    assert message in response.text
    assert items(db_session) == []
