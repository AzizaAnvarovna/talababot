"""Telegram bot jarayoni uchun ichki API."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Message
from app.db.session import get_db
from app.dialog import list_topics
from app.kb_import import CATEGORIES
from app.outbox import mark_delivered, pending_for_telegram
from app.security import secrets_match


def require_bot_token(x_internal_token: str | None = Header(default=None)) -> None:
    if not secrets_match(x_internal_token, get_settings().bot_api_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ichki token notoʻgʻri")


router = APIRouter(
    prefix="/api/internal",
    tags=["internal"],
    dependencies=[Depends(require_bot_token)],
    include_in_schema=False,
)


@router.get("/pending")
def pending(db: Session = Depends(get_db)) -> list[dict]:
    return pending_for_telegram(db)


@router.post("/messages/{message_id}/delivered")
def delivered(message_id: int, db: Session = Depends(get_db)) -> dict:
    message = db.get(Message, message_id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xabar topilmadi")
    mark_delivered(message)
    db.commit()
    return {"ok": True}


@router.get("/topics")
def topics(category: str = Query(max_length=64), db: Session = Depends(get_db)) -> list[dict]:
    """Bot menyusi: boʻlimdagi tekshirilgan mavzular."""
    if category not in CATEGORIES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Boʻlim topilmadi")
    return list_topics(db, category)
