"""Admin bosh sahifasi uchun qisqa holat: pilot raqamlari, navbat, bilimlar bazasi, tizim."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AhpJudgment, Dialog, Handoff, KbItem, Message, User
from app.db.models import utcnow as _utcnow
from app.metrics.indicators import LOCAL_OFFSET
from app.settings_store import RuntimeSettings, load_settings

DAYS = 14


@dataclass
class Dashboard:
    today: date
    dialogs_total: int
    dialogs_today: int
    students: int
    resolved_share: float | None
    csat_avg: float | None
    pending_handoffs: int
    kb_total: int
    kb_verified: int
    ahp_done: bool
    last_message_at: datetime | None
    daily: list[dict] = field(default_factory=list)
    categories: list[dict] = field(default_factory=list)
    settings: RuntimeSettings | None = None
    test_mode: bool = False

    @property
    def daily_max(self) -> int:
        return max((day["dialogs"] for day in self.daily), default=0)


def _local(moment: datetime) -> datetime:
    return moment + LOCAL_OFFSET


def build_dashboard(db: Session, test_mode: bool, now: datetime | None = None) -> Dashboard:
    """Faqat haqiqiy (is_test = yolgʻon) dialoglar hisoblanadi, tahlil paneli bilan bir xil."""
    now = now or _utcnow()
    today = _local(now).date()
    real = select(Dialog).where(Dialog.is_test.is_(False))
    dialogs = list(db.scalars(real))

    by_day = {today - timedelta(days=offset): 0 for offset in range(DAYS - 1, -1, -1)}
    for dialog in dialogs:
        day = _local(dialog.started_at).date()
        if day in by_day:
            by_day[day] += 1

    answered = [d.resolved for d in dialogs if d.resolved is not None]
    scores = [d.csat for d in dialogs if d.csat is not None]
    students = db.scalar(
        select(func.count(func.distinct(Dialog.user_id)))
        .join(User, User.id == Dialog.user_id)
        .where(Dialog.is_test.is_(False), User.consent.is_(True))
    )
    pending = db.scalar(
        select(func.count(Handoff.id))
        .join(Dialog, Dialog.id == Handoff.dialog_id)
        .where(Handoff.answered_at.is_(None), Dialog.is_test.is_(False))
    )
    categories = db.execute(
        select(Message.intent, func.count(func.distinct(Message.dialog_id)))
        .join(Dialog, Dialog.id == Message.dialog_id)
        .where(Dialog.is_test.is_(False), Message.sender == "talaba", Message.intent.is_not(None))
        .group_by(Message.intent)
        .order_by(func.count(func.distinct(Message.dialog_id)).desc())
    ).all()
    last = db.scalar(
        select(func.max(Message.created_at))
        .join(Dialog, Dialog.id == Message.dialog_id)
        .where(Dialog.is_test.is_(False), Message.sender == "talaba")
    )
    kb_total = db.scalar(select(func.count(KbItem.id))) or 0
    kb_verified = db.scalar(select(func.count(KbItem.id)).where(KbItem.verified.is_(True))) or 0
    levels = set(db.scalars(select(AhpJudgment.level)))

    return Dashboard(
        today=today,
        dialogs_total=len(dialogs),
        dialogs_today=by_day[today],
        students=students or 0,
        resolved_share=sum(answered) / len(answered) if answered else None,
        csat_avg=sum(scores) / len(scores) if scores else None,
        pending_handoffs=pending or 0,
        kb_total=kb_total,
        kb_verified=kb_verified,
        ahp_done=levels >= {0, 1, 2, 3},
        last_message_at=_local(last) if last else None,
        daily=[{"date": day, "dialogs": count} for day, count in by_day.items()],
        categories=[{"name": name, "dialogs": count} for name, count in categories],
        settings=load_settings(db),
        test_mode=test_mode,
    )
