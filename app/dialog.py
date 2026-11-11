"""Kanaldan mustaqil dialog mantig'i (FR-3, FR-4)."""

import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Dialog, Handoff, KbItem, Message, User, utcnow
from app.nlp.masking import mask_pii
from app.nlp.retriever import find_verified_answer
from app.security import hash_user_id

MODEL_VERSION = "stage1-stub"

CONSENT_NOTICE = (
    "Assalomu alaykum! Men TalabaBot — talabalar murojaatlari bo'yicha yordamchiman.\n\n"
    "Suhbatlar ilmiy tadqiqot maqsadida anonim saqlanadi. Rozimisiz?"
)
WELCOME = "Savolingizni yozing."
NO_ANSWER = "Kechirasiz, bu savolga javob topa olmadim. Operator bilan bog'lanishingiz mumkin."
HANDED_OFF = "Murojaatingiz operatorga uzatildi. Javobni shu yerda olasiz."
ALREADY_HANDED_OFF = "Murojaatingiz allaqachon operatorga uzatilgan."
ENDED = "Suhbat yakunlandi. Murojaatingiz uchun rahmat!"
NO_ACTIVE_DIALOG = "Faol suhbat yo'q. Savolingizni yozishingiz mumkin."


@dataclass
class Button:
    label: str
    action: str


@dataclass
class Reply:
    text: str
    response_type: str
    dialog_id: int | None = None
    buttons: list[Button] = field(default_factory=list)


CONSENT_BUTTONS = [Button("Roziman", "consent_yes"), Button("Rozi emasman", "consent_no")]
DIALOG_BUTTONS = [Button("Operator", "operator"), Button("Yakunlash", "end")]


def _get_or_create_user(db: Session, channel: str, user_id: str) -> User:
    user_hash = hash_user_id(channel, user_id)
    query = select(User).where(User.user_hash == user_hash)
    user = db.scalar(query)
    if user is not None:
        return user
    user = User(user_hash=user_hash, channel=channel)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # shu foydalanuvchining parallel so'rovi avvalroq yaratgan
        db.rollback()
        return db.scalars(query).one()
    return user


def _active_dialog(db: Session, user: User) -> Dialog | None:
    return db.scalar(
        select(Dialog)
        .where(Dialog.user_id == user.id, Dialog.ended_at.is_(None))
        .order_by(Dialog.id.desc())
    )


def _open_dialog(db: Session, user: User) -> Dialog:
    dialog = _active_dialog(db, user)
    if dialog is None:
        dialog = Dialog(
            user_id=user.id,
            channel=user.channel,
            model_version=MODEL_VERSION,
            is_test=get_settings().test_mode,
        )
        db.add(dialog)
        db.flush()
    return dialog


def _log_bot(db: Session, dialog: Dialog, text: str, response_type: str, started: float) -> None:
    db.add(
        Message(
            dialog_id=dialog.id,
            sender="bot",
            text_masked=mask_pii(text),
            response_type=response_type,
            latency_ms=round((time.perf_counter() - started) * 1000),
            delivered_at=utcnow(),
        )
    )


def _format_answer(item: KbItem) -> str:
    source = item.source or item.department
    return f"{item.answer}\n\nManba: {source}" if source else item.answer


def _answer_question(db: Session, user: User, text: str) -> Reply:
    started = time.perf_counter()
    dialog = _open_dialog(db, user)
    db.add(Message(dialog_id=dialog.id, sender="talaba", text_masked=mask_pii(text)))

    item = find_verified_answer(db, text)
    reply_text = _format_answer(item) if item else NO_ANSWER
    response_type = "kb" if item else "fallback"
    _log_bot(db, dialog, reply_text, response_type, started)
    db.commit()
    return Reply(reply_text, response_type, dialog.id, list(DIALOG_BUTTONS))


def _hand_off(db: Session, user: User) -> Reply:
    started = time.perf_counter()
    dialog = _open_dialog(db, user)
    if dialog.handed_off:
        db.commit()
        return Reply(ALREADY_HANDED_OFF, "operator", dialog.id, [Button("Yakunlash", "end")])
    dialog.handed_off = True
    db.add(Handoff(dialog_id=dialog.id))
    _log_bot(db, dialog, HANDED_OFF, "operator", started)
    db.commit()
    return Reply(HANDED_OFF, "operator", dialog.id, [Button("Yakunlash", "end")])


def _end_dialog(db: Session, user: User) -> Reply:
    dialog = _active_dialog(db, user)
    if dialog is None:
        return Reply(NO_ACTIVE_DIALOG, "system")
    dialog.ended_at = utcnow()
    dialog.end_reason = "user"
    db.commit()
    return Reply(ENDED, "system", dialog.id)


def handle_message(
    db: Session, channel: str, user_id: str, text: str | None, action: str | None
) -> Reply:
    user = _get_or_create_user(db, channel, user_id)

    if action in ("consent_yes", "consent_no"):
        user.consent = action == "consent_yes"
        db.commit()
        return Reply(WELCOME, "system")
    if user.consent is None:
        return Reply(CONSENT_NOTICE, "system", buttons=list(CONSENT_BUTTONS))
    if action == "start":
        return Reply(WELCOME, "system")
    if action == "operator":
        return _hand_off(db, user)
    if action == "end":
        return _end_dialog(db, user)
    return _answer_question(db, user, text)
