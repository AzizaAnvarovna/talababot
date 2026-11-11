"""Admin: model sozlamalari va jargon lugʻati (FR-7, FR-10, FR-14)."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import _redirect, require_admin, templates
from app.db.models import SlangTerm
from app.db.session import get_db
from app.nlp.classifier import available_models
from app.nlp.normalizer import normalize
from app.settings_store import RuntimeSettings, load_settings, save_settings

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _render_settings(
    request: Request,
    values: RuntimeSettings,
    error: str | None = None,
    flash: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "admin/settings.html",
        {"values": values, "models": available_models(), "error": error, "flash": flash},
        status_code=status.HTTP_400_BAD_REQUEST if error else status.HTTP_200_OK,
    )


def _parse_threshold(raw: str) -> float | None:
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return None
    return value if 0 <= value <= 1 else None


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    flash = request.session.pop("flash", None)
    return _render_settings(request, load_settings(db), flash=flash)


@router.post("/settings", response_class=HTMLResponse)
def settings_save(
    request: Request,
    tau: str = Form(""),
    sigma: str = Form(""),
    active_model: str = Form(""),
    ab_enabled: bool = Form(False),
    ab_model_a: str = Form(""),
    ab_model_b: str = Form(""),
    db: Session = Depends(get_db),
):
    current = load_settings(db)
    tau_value, sigma_value = _parse_threshold(tau), _parse_threshold(sigma)
    if tau_value is None or sigma_value is None:
        return _render_settings(request, current, "τ va σ 0 dan 1 gacha son boʻlishi kerak.")

    models = available_models()
    if active_model not in models:
        return _render_settings(request, current, "Bu model hali oʻqitilmagan.")
    if ab_enabled and (
        ab_model_a not in models or ab_model_b not in models or ab_model_a == ab_model_b
    ):
        return _render_settings(request, current, "A/B uchun ikki xil tayyor model tanlang.")

    save_settings(
        db,
        RuntimeSettings(
            tau=tau_value,
            sigma=sigma_value,
            active_model=active_model,
            ab_enabled=ab_enabled,
            ab_model_a=ab_model_a or current.ab_model_a,
            ab_model_b=ab_model_b or current.ab_model_b,
        ),
    )
    request.session["flash"] = "Sozlamalar saqlandi."
    return _redirect("/admin/settings")


@router.get("/slang", response_class=HTMLResponse)
def slang_list(request: Request, db: Session = Depends(get_db)):
    terms = db.scalars(select(SlangTerm).order_by(SlangTerm.term)).all()
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(request, "admin/slang.html", {"terms": terms, "flash": flash})


@router.post("/slang")
def slang_save(
    request: Request,
    term: str = Form(""),
    replacement: str = Form(""),
    db: Session = Depends(get_db),
):
    term_norm, replacement_norm = normalize(term), normalize(replacement)
    if not term_norm or not replacement_norm:
        request.session["flash"] = "Ikkala maydon ham toʻldirilishi shart."
        return _redirect("/admin/slang")
    existing = db.scalar(select(SlangTerm).where(SlangTerm.term == term_norm))
    if existing:
        existing.replacement = replacement_norm
    else:
        db.add(SlangTerm(term=term_norm, replacement=replacement_norm))
    db.commit()
    request.session["flash"] = "Lugʻat yangilandi."
    return _redirect("/admin/slang")


@router.post("/slang/{term_id}/delete")
def slang_delete(request: Request, term_id: int, db: Session = Depends(get_db)):
    term = db.get(SlangTerm, term_id)
    if term is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Yozuv topilmadi")
    db.delete(term)
    db.commit()
    request.session["flash"] = "Lugʻatdan oʻchirildi."
    return _redirect("/admin/slang")
