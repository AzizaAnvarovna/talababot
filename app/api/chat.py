import re
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.dialog import CATEGORY_ACTION_PREFIX, handle_message
from app.kb_import import CATEGORIES
from app.outbox import take_for_web
from app.security import secrets_match

router = APIRouter(prefix="/api/chat", tags=["chat"])

_VALID_ACTIONS = {"start", "consent_yes", "consent_no", "operator", "end"} | {
    f"{CATEGORY_ACTION_PREFIX}{category}" for category in CATEGORIES
}
_FEEDBACK_ACTION = re.compile(r"resolved:\d{1,12}:(?:yes|no)|rate:\d{1,12}:[1-5]|kb:\d{1,12}")


class ChatRequest(BaseModel):
    channel: Literal["telegram", "web"]
    user_id: str = Field(min_length=1, max_length=128)
    text: str | None = Field(default=None, max_length=2000)
    action: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def require_text_or_action(self) -> "ChatRequest":
        has_text = bool(self.text and self.text.strip())
        if has_text == (self.action is not None):
            raise ValueError("text yoki action dan aynan bittasi berilishi kerak")
        if (
            self.action is not None
            and self.action not in _VALID_ACTIONS
            and not _FEEDBACK_ACTION.fullmatch(self.action)
        ):
            raise ValueError("Notoʻgʻri action")
        return self


class ButtonOut(BaseModel):
    label: str
    action: str


class ChatResponse(BaseModel):
    dialog_id: int | None
    text: str
    response_type: str
    buttons: list[ButtonOut]
    category: str | None = None
    title: str | None = None


@router.post("/message", response_model=ChatResponse)
def post_message(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    x_internal_token: str | None = Header(default=None),
) -> dict:
    # Telegram foydalanuvchi ID sini faqat bot jarayoni yubora oladi.
    if payload.channel == "telegram" and not secrets_match(
        x_internal_token, get_settings().bot_api_token
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ichki token notoʻgʻri")
    reply = handle_message(db, payload.channel, payload.user_id, payload.text, payload.action)
    return asdict(reply)


class UpdatesRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)


@router.post("/updates")
def post_updates(payload: UpdatesRequest, db: Session = Depends(get_db)) -> list[dict]:
    """Veb-chat operator javoblari va baholash soʻrovlarini shu yerdan oladi."""
    return take_for_web(db, payload.user_id)
