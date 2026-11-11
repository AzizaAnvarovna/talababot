from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import HOME_BY_ROLE, LOGIN_URL, authenticate, require_admin
from app.db.models import KbItem
from app.db.session import get_db
from app.kb_import import CATEGORIES, KbImportError, import_workbook

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

_MAX_SKIPPED_SHOWN = 20


public = APIRouter(prefix="/admin", tags=["admin"])
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status.HTTP_303_SEE_OTHER)


@public.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "admin/login.html", {"error": None})


@public.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    login: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    staff = authenticate(db, login.strip(), password)
    if staff is None:
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"error": "Login yoki parol notoʻgʻri."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    request.session.clear()
    request.session["staff_id"] = staff.id
    return _redirect(HOME_BY_ROLE.get(staff.role, LOGIN_URL))


@public.post("/logout")
def logout(request: Request):
    request.session.clear()
    return _redirect(LOGIN_URL)


@router.get("")
def admin_home():
    return _redirect("/admin/kb")


@router.get("/kb", response_class=HTMLResponse)
def kb_list(request: Request, db: Session = Depends(get_db)):
    items = db.scalars(select(KbItem).order_by(KbItem.category, KbItem.intent)).all()
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        request, "admin/kb_list.html", {"items": items, "flash": flash}
    )


def _render_form(request: Request, item: dict, action: str, error: str | None = None):
    return templates.TemplateResponse(
        request,
        "admin/kb_form.html",
        {"item": item, "action": action, "error": error, "categories": CATEGORIES},
        status_code=status.HTTP_400_BAD_REQUEST if error else status.HTTP_200_OK,
    )


def _clean_form(category, intent, questions, answer, source, department, verified) -> dict:
    return {
        "category": category.strip(),
        "intent": intent.strip(),
        "questions": "\n".join(q.strip() for q in questions.splitlines() if q.strip()),
        "answer": answer.strip(),
        "source": source.strip() or None,
        "department": department.strip() or None,
        "verified": verified,
    }


def _form_error(data: dict) -> str | None:
    if data["category"] not in CATEGORIES:
        return "Toifani tanlang."
    if not (data["intent"] and data["questions"] and data["answer"]):
        return "Kichik mavzu, savol namunalari va javob toʻldirilishi shart."
    return None


def _get_item(db: Session, item_id: int) -> KbItem:
    item = db.get(KbItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")
    return item


@router.get("/kb/new", response_class=HTMLResponse)
def kb_new_form(request: Request):
    return _render_form(request, {"verified": False}, "/admin/kb/new")


@router.post("/kb/new", response_class=HTMLResponse)
def kb_create(
    request: Request,
    category: str = Form(""),
    intent: str = Form(""),
    questions: str = Form(""),
    answer: str = Form(""),
    source: str = Form(""),
    department: str = Form(""),
    verified: bool = Form(False),
    db: Session = Depends(get_db),
):
    data = _clean_form(category, intent, questions, answer, source, department, verified)
    error = _form_error(data)
    if error:
        return _render_form(request, data, "/admin/kb/new", error)
    db.add(KbItem(**data))
    db.commit()
    request.session["flash"] = "Yozuv qoʻshildi."
    return _redirect("/admin/kb")


@router.get("/kb/{item_id}/edit", response_class=HTMLResponse)
def kb_edit_form(request: Request, item_id: int, db: Session = Depends(get_db)):
    item = _get_item(db, item_id)
    return _render_form(request, item.__dict__, f"/admin/kb/{item_id}/edit")


@router.post("/kb/{item_id}/edit", response_class=HTMLResponse)
def kb_update(
    request: Request,
    item_id: int,
    category: str = Form(""),
    intent: str = Form(""),
    questions: str = Form(""),
    answer: str = Form(""),
    source: str = Form(""),
    department: str = Form(""),
    verified: bool = Form(False),
    db: Session = Depends(get_db),
):
    item = _get_item(db, item_id)
    data = _clean_form(category, intent, questions, answer, source, department, verified)
    error = _form_error(data)
    if error:
        return _render_form(request, data, f"/admin/kb/{item_id}/edit", error)
    for name, value in data.items():
        setattr(item, name, value)
    db.commit()
    request.session["flash"] = "Yozuv saqlandi."
    return _redirect("/admin/kb")


@router.post("/kb/{item_id}/delete")
def kb_delete(request: Request, item_id: int, db: Session = Depends(get_db)):
    db.delete(_get_item(db, item_id))
    db.commit()
    request.session["flash"] = "Yozuv oʻchirildi."
    return _redirect("/admin/kb")


@router.post("/kb/import")
def kb_import(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        result = import_workbook(db, file.file)
    except KbImportError as error:
        request.session["flash"] = f"Import xatosi: {error}"
        return _redirect("/admin/kb")
    message = f"Import: {result.created} ta yangi, {result.updated} ta yangilandi."
    if result.skipped_rows:
        shown = ", ".join(map(str, result.skipped_rows[:_MAX_SKIPPED_SHOWN]))
        message += f" Oʻtkazib yuborildi: {len(result.skipped_rows)} ta (qatorlar: {shown})."
    request.session["flash"] = message
    return _redirect("/admin/kb")
