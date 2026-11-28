"""Talabaga keyinroq yetkaziladigan xabarlar: operator javobi va baholash soʻrovi (FR-22)."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Dialog, Message, User, utcnow
from app.security import decrypt, hash_user_id

_BATCH_SIZE = 50


def _undelivered():
    return (
        select(Message, User)
        .join(Dialog, Message.dialog_id == Dialog.id)
        .join(User, Dialog.user_id == User.id)
        .where(Message.delivered_at.is_(None), Message.sender.in_(("bot", "operator")))
        .order_by(Message.id)
    )


def _payload(message: Message) -> dict:
    return {
        "id": message.id,
        "sender": message.sender,
        "text": decrypt(message.outbox_text) if message.outbox_text else message.text_masked,
        "buttons": json.loads(message.buttons_json or "[]"),
    }


def mark_delivered(message: Message) -> None:
    message.delivered_at = utcnow()
    message.outbox_text = None


def pending_for_telegram(db: Session) -> list[dict]:
    query = (
        _undelivered()
        .where(User.channel == "telegram", User.delivery_ref.is_not(None))
        .limit(_BATCH_SIZE)
    )
    return [
        _payload(message) | {"chat_id": decrypt(user.delivery_ref)}
        for message, user in db.execute(query)
    ]


def take_for_web(db: Session, user_id: str) -> list[dict]:
    query = _undelivered().where(User.user_hash == hash_user_id("web", user_id))
    messages = [message for message, _ in db.execute(query)]
    payloads = [_payload(message) for message in messages]
    for message in messages:
        mark_delivered(message)
    db.commit()
    return payloads
