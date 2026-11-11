from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.dialog import handle_message
from app.security import secrets_match

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    channel: Literal["telegram", "web"]
    user_id: str = Field(min_length=1, max_length=128)
    text: str | None = Field(default=None, max_length=2000)
    action: Literal["start", "consent_yes", "consent_no", "operator", "end"] | None = None

    @model_validator(mode="after")
    def require_text_or_action(self) -> "ChatRequest":
        has_text = bool(self.text and self.text.strip())
        if has_text == (self.action is not None):
            raise ValueError("text yoki action dan aynan bittasi berilishi kerak")
        return self


class ButtonOut(BaseModel):
    label: str
    action: str


class ChatResponse(BaseModel):
    dialog_id: int | None
    text: str
    response_type: str
    buttons: list[ButtonOut]


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
