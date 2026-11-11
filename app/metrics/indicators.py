"""k1–k8 va kS koʻrsatkichlarini loglardan hisoblash (TZ 4.8, 4.8.1)."""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from statistics import mean

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import Dialog, ExpertRating, Message, ModelVersion, User

TARGET_TURNS = 2
MAX_RESPONSE_SECONDS = 5
NEGATIVE_SENTIMENT = -0.25
# Sanalar Oʻzbekiston vaqtida guruhlanadi; bazada UTC saqlanadi.
LOCAL_OFFSET = timedelta(hours=5)
_KEEP = object()


@dataclass
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    model: str | None = None
    channel: str | None = None
    include_test: bool = False


@dataclass
class DialogStat:
    channel: str = "web"
    local_date: date = date(2026, 1, 1)
    resolved: bool | None = None
    csat: int | None = None
    handed_off: bool = False
    student_messages: int = 0
    had_fallback: bool = False
    latencies: list[int] = field(default_factory=list)
    sentiments: list[float] = field(default_factory=list)
    category: str | None = None
    expert_scores: list[int] = field(default_factory=list)


def _dialog_ids(filters: Filters) -> Select:
    query = (
        select(Dialog.id)
        .join(User, Dialog.user_id == User.id)
        .where(Dialog.ended_at.is_not(None), User.consent.is_(True))
    )
    if not filters.include_test:
        query = query.where(Dialog.is_test.is_(False))
    if filters.date_from:
        query = query.where(
            Dialog.started_at >= datetime.combine(filters.date_from, time.min) - LOCAL_OFFSET
        )
    if filters.date_to:
        next_day = filters.date_to + timedelta(days=1)
        query = query.where(Dialog.started_at < datetime.combine(next_day, time.min) - LOCAL_OFFSET)
    if filters.model:
        query = query.where(Dialog.model_version == filters.model)
    if filters.channel:
        query = query.where(Dialog.channel == filters.channel)
    return query


def load_stats(db: Session, filters: Filters) -> list[DialogStat]:
    ids = _dialog_ids(filters)
    stats = {
        dialog.id: DialogStat(
            channel=dialog.channel,
            local_date=(dialog.started_at + LOCAL_OFFSET).date(),
            resolved=dialog.resolved,
            csat=dialog.csat,
            handed_off=dialog.handed_off,
        )
        for dialog in db.scalars(select(Dialog).where(Dialog.id.in_(ids)))
    }
    messages = db.execute(
        select(
            Message.dialog_id,
            Message.sender,
            Message.response_type,
            Message.latency_ms,
            Message.sentiment,
            Message.intent,
        )
        .where(Message.dialog_id.in_(ids))
        .order_by(Message.id)
    )
    for dialog_id, sender, response_type, latency, sentiment, intent in messages:
        stat = stats[dialog_id]
        if sender == "talaba":
            stat.student_messages += 1
            if sentiment is not None:
                stat.sentiments.append(sentiment)
            if intent is not None:
                stat.category = intent
        elif sender == "bot":
            stat.had_fallback = stat.had_fallback or response_type == "fallback"
            if latency is not None:
                stat.latencies.append(latency)
    ratings = db.execute(
        select(ExpertRating.dialog_id, ExpertRating.score).where(ExpertRating.dialog_id.in_(ids))
    )
    for dialog_id, score in ratings:
        stats[dialog_id].expert_scores.append(score)
    return list(stats.values())


def model_k1(db: Session, model: str) -> float | None:
    """k1 eksperiment modulidan keladi (FR-32)."""
    raw = db.scalar(select(ModelVersion.metrics_json).where(ModelVersion.name == model))
    return json.loads(raw).get("macro_f1") if raw else None


def _is_negative(stat: DialogStat) -> bool:
    return bool(stat.sentiments) and mean(stat.sentiments) < NEGATIVE_SENTIMENT


def k2_from(stats: list[DialogStat]) -> float | None:
    scores = [score for stat in stats for score in stat.expert_scores]
    return (mean(scores) - 1) / 4 if scores else None


def compute(stats: list[DialogStat], k1: float | None, k2=_KEEP) -> dict[str, float | None]:
    """k2 berilsa (kunlik dinamika uchun) loglardan qayta hisoblanmaydi."""
    total = len(stats)
    empty = dict.fromkeys(("k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "kS"))
    if total == 0:
        return empty

    resolved = [stat.resolved for stat in stats if stat.resolved is not None]
    csat = [stat.csat for stat in stats if stat.csat is not None]
    latencies = [value for stat in stats for value in stat.latencies]
    turns = mean(stat.student_messages for stat in stats)
    return {
        "k1": k1,
        "k2": k2_from(stats) if k2 is _KEEP else k2,
        "k3": 1 - sum(stat.had_fallback for stat in stats) / total,
        "k4": sum(resolved) / len(resolved) if resolved else None,
        "k5": 1 - sum(stat.handed_off for stat in stats) / total,
        "k6": min(1.0, TARGET_TURNS / turns) if turns else None,
        "k7": max(0.0, 1 - mean(latencies) / 1000 / MAX_RESPONSE_SECONDS) if latencies else None,
        "k8": (mean(csat) - 1) / 4 if csat else None,
        "kS": 1 - sum(_is_negative(stat) for stat in stats) / total,
    }
