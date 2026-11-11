"""Ekspert sahifalari: dialoglarni baholash (FR-28) va AHP soʻrovnomasi (FR-25)."""

import json
import random

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from app.api.admin import _redirect, templates
from app.auth import require_roles
from app.config import get_settings
from app.db.models import AhpJudgment, Dialog, ExpertRating, Message, Staff, User
from app.db.session import get_db
from app.metrics import ahp
from app.metrics.integral import LABELS, LEVELS

require_expert = require_roles("ekspert", "admin")
router = APIRouter(prefix="/expert", tags=["expert"], dependencies=[Depends(require_expert)])

RATING_TARGET = 50
_LEVEL_TITLES = {
    0: "Oʻlchamlar oʻzaro",
    1: "QD1 — Tushunish ichida",
    2: "QD2 — Samaradorlik ichida",
    3: "QD3 — Tajriba ichida",
}
SCALE = {f"1/{n}": 1 / n for n in range(9, 1, -1)} | {str(n): float(n) for n in range(1, 10)}


async def form_data(request: Request) -> FormData:
    return await request.form()


def _eligible_dialogs():
    """Test rejimida faqat test dialoglari, pilotda faqat haqiqiy dialoglar baholanadi."""
    has_student_message = select(Message.dialog_id).where(Message.sender == "talaba")
    return (
        select(Dialog.id)
        .join(User, Dialog.user_id == User.id)
        .where(
            Dialog.ended_at.is_not(None),
            User.consent.is_(True),
            Dialog.is_test.is_(get_settings().test_mode),
            Dialog.id.in_(has_student_message),
        )
    )


def _rated_ids(db: Session, expert: Staff) -> set[int]:
    query = select(ExpertRating.dialog_id).where(ExpertRating.expert_id == expert.id)
    return set(db.scalars(query))


@router.get("", response_class=HTMLResponse)
def rate_page(
    request: Request, expert: Staff = Depends(require_expert), db: Session = Depends(get_db)
):
    rated = _rated_ids(db, expert)
    candidates = sorted(set(db.scalars(_eligible_dialogs())) - rated)
    dialog_id = random.choice(candidates) if candidates and len(rated) < RATING_TARGET else None
    messages = []
    if dialog_id is not None:
        messages = db.scalars(
            select(Message).where(Message.dialog_id == dialog_id).order_by(Message.id)
        ).all()
    return templates.TemplateResponse(
        request,
        "expert/rate.html",
        {
            "dialog_id": dialog_id,
            "messages": messages,
            "rated": len(rated),
            "target": RATING_TARGET,
            "flash": request.session.pop("flash", None),
        },
    )


@router.post("/rate/{dialog_id}")
def rate(
    dialog_id: int,
    score: int = Form(0),
    expert: Staff = Depends(require_expert),
    db: Session = Depends(get_db),
):
    if not 1 <= score <= 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ball 1 dan 5 gacha boʻlishi kerak")
    if db.scalar(_eligible_dialogs().where(Dialog.id == dialog_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dialog topilmadi")
    if dialog_id not in _rated_ids(db, expert):
        db.add(ExpertRating(dialog_id=dialog_id, expert_id=expert.id, score=score))
        db.commit()
    return _redirect("/expert")


def _closest_scale_key(value: float) -> str:
    return min(SCALE, key=lambda key: abs(SCALE[key] - value))


def _ahp_context(db: Session, expert: Staff, error: str | None, flash: str | None) -> dict:
    query = select(AhpJudgment).where(AhpJudgment.expert_id == expert.id)
    saved = {row.level: json.loads(row.matrix_json) for row in db.scalars(query)}
    levels = []
    for level, codes in LEVELS.items():
        pairs = [
            {
                "field": f"m{level}_{i}_{j}",
                "a": LABELS[codes[i]],
                "b": LABELS[codes[j]],
                "value": _closest_scale_key(saved[level][i][j]) if level in saved else "1",
            }
            for i in range(len(codes))
            for j in range(i + 1, len(codes))
        ]
        levels.append({"title": _LEVEL_TITLES[level], "pairs": pairs})
    return {
        "levels": levels,
        "scale": list(SCALE),
        "error": error,
        "flash": flash,
    }


@router.get("/ahp", response_class=HTMLResponse)
def ahp_page(
    request: Request, expert: Staff = Depends(require_expert), db: Session = Depends(get_db)
):
    flash = request.session.pop("flash", None)
    context = _ahp_context(db, expert, None, flash)
    return templates.TemplateResponse(request, "expert/ahp.html", context)


def _parse_matrices(form: FormData) -> dict[int, ahp.Matrix] | None:
    matrices = {}
    for level, codes in LEVELS.items():
        size = len(codes)
        upper = {}
        for i in range(size):
            for j in range(i + 1, size):
                value = SCALE.get(str(form.get(f"m{level}_{i}_{j}", "")))
                if value is None:
                    return None
                upper[(i, j)] = value
        matrices[level] = ahp.reciprocal_matrix(size, upper)
    return matrices


@router.post("/ahp", response_class=HTMLResponse)
def ahp_save(
    request: Request,
    form: FormData = Depends(form_data),
    expert: Staff = Depends(require_expert),
    db: Session = Depends(get_db),
):
    matrices = _parse_matrices(form)
    if matrices is None:
        context = _ahp_context(db, expert, "Barcha juftliklarni 1–9 shkalada tanlang.", None)
        return templates.TemplateResponse(
            request, "expert/ahp.html", context, status_code=status.HTTP_400_BAD_REQUEST
        )

    previous = select(AhpJudgment).where(AhpJudgment.expert_id == expert.id)
    for judgment in db.scalars(previous):
        db.delete(judgment)
    warnings = []
    for level, matrix in matrices.items():
        ratio = ahp.consistency_ratio(matrix)
        db.add(
            AhpJudgment(expert_id=expert.id, level=level, matrix_json=json.dumps(matrix), cr=ratio)
        )
        if ratio >= ahp.CR_LIMIT:
            warnings.append(f"{_LEVEL_TITLES[level]} (CR = {ratio:.2f})")
    db.commit()
    request.session["flash"] = (
        "Saqlandi, lekin baholar izchil emas (CR ≥ 0,10), qayta koʻrib chiqing: "
        + "; ".join(warnings)
        if warnings
        else "Saqlandi. Baholar izchil."
    )
    return _redirect("/expert/ahp")
