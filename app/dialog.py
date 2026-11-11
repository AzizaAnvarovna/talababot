"""Kanaldan mustaqil dialog mantigʻi (FR-3, FR-4, FR-10 – FR-14)."""

import random
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Dialog, Handoff, KbItem, Message, User, utcnow
from app.nlp.classifier import get_classifier
from app.nlp.masking import mask_pii
from app.nlp.normalizer import normalize
from app.nlp.retriever import best_match
from app.nlp.strategy import Decision, decide
from app.security import hash_user_id
from app.settings_store import RuntimeSettings, load_settings, load_slang

CATEGORY_ACTION_PREFIX = "category:"
CONTEXT_TTL = timedelta(minutes=10)

CONSENT_NOTICE = (
    "Assalomu alaykum! Men TalabaBot — talabalar murojaatlari boʻyicha yordamchiman.\n\n"
    "Suhbatlar ilmiy tadqiqot maqsadida anonim saqlanadi. Rozimisiz?"
)
WELCOME = "Savolingizni yozing."
HANDED_OFF = "Murojaatingiz operatorga uzatildi. Javobni shu yerda olasiz."
ALREADY_HANDED_OFF = "Murojaatingiz allaqachon operatorga uzatilgan."
NOT_UNDERSTOOD = "Kechirasiz, savolingizni tushuna olmadim. Murojaatingiz operatorga uzatildi."
ENDED = "Suhbat yakunlandi. Murojaatingiz uchun rahmat!"
NO_ACTIVE_DIALOG = "Faol suhbat yoʻq. Savolingizni yozishingiz mumkin."

_OPERATOR_WORD = re.compile(r"(?<!\w)operator")


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
END_BUTTON = Button("Yakunlash", "end")
DIALOG_BUTTONS = [Button("Operator", "operator"), END_BUTTON]


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
    except IntegrityError:  # shu foydalanuvchining parallel soʻrovi avvalroq yaratgan
        db.rollback()
        return db.scalars(query).one()
    return user


def _active_dialog(db: Session, user: User) -> Dialog | None:
    return db.scalar(
        select(Dialog)
        .where(Dialog.user_id == user.id, Dialog.ended_at.is_(None))
        .order_by(Dialog.id.desc())
    )


def _choose_model(settings: RuntimeSettings) -> str:
    if settings.ab_enabled:
        return random.choice((settings.ab_model_a, settings.ab_model_b))
    return settings.active_model


def _open_dialog(db: Session, user: User, settings: RuntimeSettings) -> Dialog:
    dialog = _active_dialog(db, user)
    if dialog is None:
        dialog = Dialog(
            user_id=user.id,
            channel=user.channel,
            model_version=_choose_model(settings),
            is_test=get_settings().test_mode,
        )
        db.add(dialog)
        db.flush()
    return dialog


def _log_bot(
    db: Session,
    dialog: Dialog,
    text: str,
    response_type: str,
    started: float,
    intent: str | None = None,
) -> None:
    db.add(
        Message(
            dialog_id=dialog.id,
            sender="bot",
            text_masked=mask_pii(text),
            intent=intent,
            response_type=response_type,
            latency_ms=round((time.perf_counter() - started) * 1000),
            delivered_at=utcnow(),
        )
    )


def _last_bot_message(db: Session, dialog: Dialog) -> Message | None:
    return db.scalar(
        select(Message)
        .where(Message.dialog_id == dialog.id, Message.sender == "bot")
        .order_by(Message.id.desc())
    )


def _context_category(db: Session, dialog: Dialog) -> str | None:
    return db.scalar(
        select(Message.intent)
        .where(
            Message.dialog_id == dialog.id,
            Message.response_type == "kb",
            Message.created_at >= utcnow() - CONTEXT_TTL,
        )
        .order_by(Message.id.desc())
    )


def _last_question(db: Session, dialog: Dialog) -> str | None:
    return db.scalar(
        select(Message.text_norm)
        .where(
            Message.dialog_id == dialog.id,
            Message.sender == "talaba",
            Message.text_norm.is_not(None),
        )
        .order_by(Message.id.desc())
    )


def _format_answer(item: KbItem) -> str:
    source = item.source or item.department
    return f"{item.answer}\n\nManba: {source}" if source else item.answer


def _mark_handed_off(db: Session, dialog: Dialog) -> None:
    if not dialog.handed_off:
        dialog.handed_off = True
        db.add(Handoff(dialog_id=dialog.id))


def _apply_decision(db: Session, dialog: Dialog, decision: Decision, started: float) -> Reply:
    if decision.kind == "kb":
        text = _format_answer(decision.item)
        _log_bot(db, dialog, text, "kb", started, intent=decision.category)
        reply = Reply(text, "kb", dialog.id, list(DIALOG_BUTTONS))
    elif decision.kind == "clarify":
        text = "Savolingiz " + " yoki ".join(f"“{o}”" for o in decision.options) + " haqidami?"
        buttons = [Button(o, f"{CATEGORY_ACTION_PREFIX}{o}") for o in decision.options]
        _log_bot(db, dialog, text, "clarify", started)
        reply = Reply(text, "clarify", dialog.id, buttons + DIALOG_BUTTONS)
    else:
        _mark_handed_off(db, dialog)
        _log_bot(db, dialog, NOT_UNDERSTOOD, "fallback", started)
        reply = Reply(NOT_UNDERSTOOD, "fallback", dialog.id, [END_BUTTON])
    db.commit()
    return reply


def _hand_off(db: Session, dialog: Dialog, started: float) -> Reply:
    if dialog.handed_off:
        db.commit()
        return Reply(ALREADY_HANDED_OFF, "operator", dialog.id, [END_BUTTON])
    _mark_handed_off(db, dialog)
    _log_bot(db, dialog, HANDED_OFF, "operator", started)
    db.commit()
    return Reply(HANDED_OFF, "operator", dialog.id, [END_BUTTON])


def _previous_was_clarify(db: Session, dialog: Dialog) -> bool:
    last = _last_bot_message(db, dialog)
    return last is not None and last.response_type == "clarify"


def _answer_question(db: Session, user: User, text: str) -> Reply:
    started = time.perf_counter()
    settings = load_settings(db)
    slang = load_slang(db)
    dialog = _open_dialog(db, user, settings)
    masked = mask_pii(text)
    query = normalize(masked, slang)

    if _OPERATOR_WORD.search(query):
        db.add(Message(dialog_id=dialog.id, sender="talaba", text_masked=masked, text_norm=query))
        return _hand_off(db, dialog, started)

    ranked = get_classifier(dialog.model_version).predict(query)
    decision = decide(
        ranked,
        query,
        settings.tau,
        settings.sigma,
        _context_category(db, dialog),
        _previous_was_clarify(db, dialog),
        lambda q, category: best_match(db, q, category, slang),
    )
    db.add(
        Message(
            dialog_id=dialog.id,
            sender="talaba",
            text_masked=masked,
            text_norm=query,
            intent=ranked[0][0],
            confidence=ranked[0][1],
        )
    )
    return _apply_decision(db, dialog, decision, started)


def _answer_in_category(db: Session, user: User, category: str) -> Reply:
    """Aniqlashtirish tugmasi bosilganda oxirgi savolga shu toifa ichidan javob qidiradi."""
    started = time.perf_counter()
    dialog = _active_dialog(db, user)
    query = _last_question(db, dialog) if dialog else None
    if query is None:
        return Reply(NO_ACTIVE_DIALOG, "system")

    settings = load_settings(db)
    slang = load_slang(db)
    decision = decide(
        [(category, 1.0)],
        query,
        settings.tau,
        settings.sigma,
        None,
        True,  # tanlangan toifada ham topilmasa, bu ketma-ket ikkinchi tushunilmagan holat
        lambda q, name: best_match(db, q, name, slang),
    )
    db.add(
        Message(
            dialog_id=dialog.id,
            sender="talaba",
            text_masked=category,
            text_norm=query,
            intent=category,
            confidence=1.0,
        )
    )
    return _apply_decision(db, dialog, decision, started)


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
        return _hand_off(db, _open_dialog(db, user, load_settings(db)), time.perf_counter())
    if action == "end":
        return _end_dialog(db, user)
    if action is not None:
        return _answer_in_category(db, user, action.removeprefix(CATEGORY_ACTION_PREFIX))
    return _answer_question(db, user, text)
