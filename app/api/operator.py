"""Operator paneli (FR-21, FR-22)."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import _redirect, templates
from app.auth import require_operator
from app.db.models import Dialog, Handoff, Message, Staff
from app.db.session import get_db
from app.dialog import answer_handoff

router = APIRouter(prefix="/operator", tags=["operator"], dependencies=[Depends(require_operator)])

_MAX_REPLY_LENGTH = 2000


def _category(db: Session, dialog_id: int) -> str | None:
    return db.scalar(
        select(Message.intent)
        .where(Message.dialog_id == dialog_id, Message.intent.is_not(None))
        .order_by(Message.id.desc())
    )


@router.get("", response_class=HTMLResponse)
def queue(request: Request, db: Session = Depends(get_db)):
    pending = db.execute(
        select(Handoff, Dialog)
        .join(Dialog, Handoff.dialog_id == Dialog.id)
        .where(Handoff.status == "pending")
        .order_by(Handoff.created_at)
    ).all()
    rows = [
        {"handoff": handoff, "channel": dialog.channel, "category": _category(db, dialog.id)}
        for handoff, dialog in pending
    ]
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        request, "operator/queue.html", {"rows": rows, "flash": flash}
    )


def _get_handoff(db: Session, handoff_id: int) -> Handoff:
    handoff = db.get(Handoff, handoff_id)
    if handoff is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Murojaat topilmadi")
    return handoff


@router.get("/{handoff_id}", response_class=HTMLResponse)
def detail(request: Request, handoff_id: int, db: Session = Depends(get_db)):
    handoff = _get_handoff(db, handoff_id)
    messages = db.scalars(
        select(Message).where(Message.dialog_id == handoff.dialog_id).order_by(Message.id)
    ).all()
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        request,
        "operator/detail.html",
        {
            "handoff": handoff,
            "dialog": db.get(Dialog, handoff.dialog_id),
            "category": _category(db, handoff.dialog_id),
            "messages": messages,
            "flash": flash,
            "max_length": _MAX_REPLY_LENGTH,
        },
    )


@router.post("/{handoff_id}/reply")
def reply(
    request: Request,
    handoff_id: int,
    text: str = Form(""),
    staff: Staff = Depends(require_operator),
    db: Session = Depends(get_db),
):
    handoff = _get_handoff(db, handoff_id)
    text = text.strip()
    if handoff.status != "pending":
        request.session["flash"] = "Bu murojaat allaqachon yopilgan."
        return _redirect("/operator")
    if not text or len(text) > _MAX_REPLY_LENGTH:
        request.session["flash"] = f"Javob 1–{_MAX_REPLY_LENGTH} belgi boʻlishi kerak."
        return _redirect(f"/operator/{handoff_id}")
    answer_handoff(db, handoff, staff.id, text)
    request.session["flash"] = "Javob talabaga yuborildi."
    return _redirect("/operator")
