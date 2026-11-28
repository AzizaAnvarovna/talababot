"""Kanaldan mustaqil dialog mantigʻi (FR-3, FR-4, FR-10 – FR-14, FR-18 – FR-22)."""

import json
import random
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Dialog, Handoff, KbItem, Message, User, utcnow
from app.nlp.classifier import get_classifier
from app.nlp.masking import mask_pii
from app.nlp.normalizer import normalize
from app.nlp.retriever import best_match
from app.nlp.sentiment import score as sentiment_score
from app.nlp.strategy import Decision, decide
from app.security import encrypt, hash_user_id
from app.settings_store import RuntimeSettings, load_settings, load_slang

CATEGORY_ACTION_PREFIX = "category:"
KB_ACTION_PREFIX = "kb:"
CONTEXT_TTL = timedelta(minutes=10)
INACTIVITY_LIMIT = timedelta(minutes=10)

CONSENT_NOTICE = (
    "Assalomu alaykum! Men TalabaBot — talabalar murojaatlari boʻyicha yordamchiman.\n\n"
    "Suhbatlar ilmiy tadqiqot maqsadida anonim saqlanadi. Rozimisiz?"
)
WELCOME = "Savolingizni yozing."
HANDED_OFF = "Murojaatingiz operatorga uzatildi. Javobni shu yerda olasiz."
ALREADY_HANDED_OFF = "Murojaatingiz allaqachon operatorga uzatilgan."
NOT_UNDERSTOOD = "Kechirasiz, savolingizni tushuna olmadim. Murojaatingiz operatorga uzatildi."
WAITING_FOR_OPERATOR = "Murojaatingiz operatorda. Javobni shu yerda olasiz."
END_PROMPT = "Suhbat yakunlandi. Muammoingiz hal boʻldimi?"
RATE_PROMPT = "Xizmatni 1 dan 5 gacha baholang."
THANKS = "Rahmat! Yangi savolingiz boʻlsa, yozishingiz mumkin."
NO_ACTIVE_DIALOG = "Faol suhbat yoʻq. Savolingizni yozishingiz mumkin."
YOU_ARE_WELCOME = "Arzimaydi! Yangi savolingiz boʻlsa, yozishingiz mumkin."
TOPIC_GONE = "Bu mavzu hozir mavjud emas. Savolingizni yozib yuboring."

_OPERATOR_WORD = re.compile(r"(?<!\w)operator")
_CLOSING_WORDS = frozenset({"rahmat", "raxmat", "tashakkur", "xayr"})
_CLOSING_FILLERS = frozenset({"katta", "juda", "koʻp", "kop", "sizga", "sizlarga", "kattakon"})


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
    # Bilimlar bazasi javobi uchun: Telegram'da sarlavha va boʻlim belgisini chizishga.
    category: str | None = None
    title: str | None = None


CONSENT_BUTTONS = [Button("Roziman", "consent_yes"), Button("Rozi emasman", "consent_no")]
END_BUTTON = Button("Yakunlash", "end")
DIALOG_BUTTONS = [Button("Operator", "operator"), END_BUTTON]


def _resolved_buttons(dialog_id: int) -> list[Button]:
    return [Button("Ha", f"resolved:{dialog_id}:yes"), Button("Yoʻq", f"resolved:{dialog_id}:no")]


def _rate_buttons(dialog_id: int) -> list[Button]:
    return [Button(str(score), f"rate:{dialog_id}:{score}") for score in range(1, 6)]


def _get_or_create_user(db: Session, channel: str, user_id: str) -> User:
    user_hash = hash_user_id(channel, user_id)
    query = select(User).where(User.user_hash == user_hash)
    user = db.scalar(query)
    if user is not None:
        return user
    # Telegramda shaxsiy chat ID si foydalanuvchi ID si bilan bir xil.
    delivery_ref = encrypt(user_id) if channel == "telegram" else None
    user = User(user_hash=user_hash, channel=channel, delivery_ref=delivery_ref)
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


def kb_title(item: KbItem) -> str:
    """Mavzu sarlavhasi — birinchi savol namunasi."""
    return next((line.strip() for line in item.questions.splitlines() if line.strip()), item.intent)


def list_topics(db: Session, category: str) -> list[dict]:
    """Boʻlimdagi tekshirilgan mavzular (bot menyusi uchun)."""
    items = db.scalars(
        select(KbItem)
        .where(KbItem.category == category, KbItem.verified.is_(True))
        .order_by(KbItem.id)
    )
    return [{"id": item.id, "title": kb_title(item)} for item in items]


def _format_answer(item: KbItem) -> str:
    """Javob, soʻng talaba murojaat qiladigan joy va rasmiy manba (ikkalasi ham boʻlsa ikkalasi)."""
    extra = []
    if item.department:
        extra.append(f"Masʼul boʻlim: {item.department}")
    if item.source:
        extra.append(f"Manba: {item.source}")
    return item.answer + ("\n\n" + "\n".join(extra) if extra else "")


def _mark_handed_off(db: Session, dialog: Dialog) -> None:
    if not dialog.handed_off:
        dialog.handed_off = True
        db.add(Handoff(dialog_id=dialog.id))


def _apply_decision(db: Session, dialog: Dialog, decision: Decision, started: float) -> Reply:
    if decision.kind == "kb":
        text = _format_answer(decision.item)
        _log_bot(db, dialog, text, "kb", started, intent=decision.category)
        reply = Reply(
            text,
            "kb",
            dialog.id,
            list(DIALOG_BUTTONS),
            category=decision.item.category,
            title=kb_title(decision.item),
        )
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


def _student_message(dialog: Dialog, masked: str, query: str, **fields) -> Message:
    return Message(
        dialog_id=dialog.id,
        sender="talaba",
        text_masked=masked,
        text_norm=query,
        sentiment=sentiment_score(query),
        **fields,
    )


def _is_closing(query: str) -> bool:
    tokens = set(re.findall(r"\w+", query))
    return bool(tokens & _CLOSING_WORDS) and tokens <= _CLOSING_WORDS | _CLOSING_FILLERS


def _answer_question(db: Session, user: User, text: str) -> Reply:
    started = time.perf_counter()
    settings = load_settings(db)
    slang = load_slang(db)
    masked = mask_pii(text)
    query = normalize(masked, slang)

    active = _active_dialog(db, user)
    if active is not None and active.handed_off:
        db.add(_student_message(active, masked, query))
        _log_bot(db, active, WAITING_FOR_OPERATOR, "operator", started)
        db.commit()
        return Reply(WAITING_FOR_OPERATOR, "operator", active.id, [END_BUTTON])
    if _is_closing(query):
        if active is None:
            return Reply(YOU_ARE_WELCOME, "system")
        db.add(_student_message(active, masked, query))
        return _finish(db, active, "closing")

    dialog = _open_dialog(db, user, settings)
    if _OPERATOR_WORD.search(query):
        db.add(_student_message(dialog, masked, query))
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
    db.add(_student_message(dialog, masked, query, intent=ranked[0][0], confidence=ranked[0][1]))
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


def _answer_kb_item(db: Session, user: User, item_id: int) -> Reply:
    """Menyudan tanlangan mavzuga toʻgʻridan-toʻgʻri javob (tasniflagichsiz)."""
    started = time.perf_counter()
    item = db.get(KbItem, item_id)
    if item is None or not item.verified:
        return Reply(TOPIC_GONE, "system")
    title = kb_title(item)
    active = _active_dialog(db, user)
    if active is not None and active.handed_off:
        db.add(_student_message(active, title, normalize(title, load_slang(db))))
        _log_bot(db, active, WAITING_FOR_OPERATOR, "operator", started)
        db.commit()
        return Reply(WAITING_FOR_OPERATOR, "operator", active.id, [END_BUTTON])
    dialog = _open_dialog(db, user, load_settings(db))
    db.add(
        _student_message(
            dialog,
            title,
            normalize(title, load_slang(db)),
            intent=item.category,
            confidence=1.0,
        )
    )
    return _apply_decision(
        db, dialog, Decision(kind="kb", item=item, category=item.category), started
    )


def _close(db: Session, dialog: Dialog, reason: str) -> None:
    dialog.ended_at = utcnow()
    dialog.end_reason = reason
    pending = select(Handoff).where(Handoff.dialog_id == dialog.id, Handoff.status == "pending")
    for handoff in db.scalars(pending):
        handoff.status = "cancelled"


def _finish(db: Session, dialog: Dialog, reason: str) -> Reply:
    _close(db, dialog, reason)
    db.commit()
    return Reply(END_PROMPT, "system", dialog.id, _resolved_buttons(dialog.id))


def _end_dialog(db: Session, user: User) -> Reply:
    dialog = _active_dialog(db, user)
    if dialog is None:
        return Reply(NO_ACTIVE_DIALOG, "system")
    return _finish(db, dialog, "user")


def _save_feedback(db: Session, user: User, action: str) -> Reply:
    kind, dialog_id, value = action.split(":")
    dialog = db.get(Dialog, int(dialog_id))
    if dialog is None or dialog.user_id != user.id or dialog.ended_at is None:
        return Reply(NO_ACTIVE_DIALOG, "system")
    if kind == "resolved":
        if dialog.resolved is None:
            dialog.resolved = value == "yes"
            db.commit()
        return Reply(RATE_PROMPT, "system", dialog.id, _rate_buttons(dialog.id))
    if dialog.csat is None:
        dialog.csat = int(value)
        db.commit()
    return Reply(THANKS, "system", dialog.id)


def _queue_end_prompt(db: Session, dialog: Dialog) -> None:
    buttons = [asdict(button) for button in _resolved_buttons(dialog.id)]
    db.add(
        Message(
            dialog_id=dialog.id,
            sender="bot",
            text_masked=END_PROMPT,
            response_type="system",
            buttons_json=json.dumps(buttons, ensure_ascii=False),
        )
    )


def answer_handoff(db: Session, handoff: Handoff, operator_id: int, text: str) -> None:
    """Operator javobi navbatga qoʻyiladi; bot va veb-chat uni talabaga yetkazadi (FR-22)."""
    dialog = db.get(Dialog, handoff.dialog_id)
    handoff.status = "answered"
    handoff.operator_id = operator_id
    handoff.answered_at = utcnow()
    db.add(
        Message(
            dialog_id=dialog.id,
            sender="operator",
            text_masked=mask_pii(text),
            response_type="operator",
            outbox_text=encrypt(text),
        )
    )
    _close(db, dialog, "operator")
    _queue_end_prompt(db, dialog)
    db.commit()


def close_inactive_dialogs(db: Session, now: datetime | None = None) -> int:
    """Faolsiz dialoglarni yopadi; operator javobini kutayotganlariga tegmaydi (FR-18)."""
    cutoff = (now or utcnow()) - INACTIVITY_LIMIT
    last = (
        select(Message.dialog_id, func.max(Message.created_at).label("at"))
        .group_by(Message.dialog_id)
        .subquery()
    )
    stale = db.scalars(
        select(Dialog)
        .outerjoin(last, Dialog.id == last.c.dialog_id)
        .where(
            Dialog.ended_at.is_(None),
            Dialog.handed_off.is_(False),
            func.coalesce(last.c.at, Dialog.started_at) < cutoff,
        )
    ).all()
    for dialog in stale:
        _close(db, dialog, "timeout")
        _queue_end_prompt(db, dialog)
    db.commit()
    return len(stale)


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
    if action is not None and action.startswith(("resolved:", "rate:")):
        return _save_feedback(db, user, action)
    if action is not None and action.startswith(KB_ACTION_PREFIX):
        return _answer_kb_item(db, user, int(action.removeprefix(KB_ACTION_PREFIX)))
    if action is not None:
        return _answer_in_category(db, user, action.removeprefix(CATEGORY_ACTION_PREFIX))
    return _answer_question(db, user, text)
