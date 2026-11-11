"""Tahlil paneli, A/B taqqoslash va eksport (FR-26, FR-27, FR-29)."""

import csv
from dataclasses import asdict
from datetime import date
from io import BytesIO, StringIO

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import templates
from app.auth import require_admin
from app.db.models import Dialog
from app.db.session import get_db
from app.metrics.indicators import Filters
from app.metrics.integral import LABELS, LEVELS
from app.metrics.report import (
    ab_table,
    build_ab,
    build_report,
    categories_table,
    daily_table,
    report_table,
)
from app.nlp.classifier import available_models
from app.settings_store import load_settings

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _parse_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def parse_filters(
    date_from: str = Query(""),
    date_to: str = Query(""),
    model: str = Query(""),
    channel: str = Query(""),
    include_test: str = Query(""),
) -> Filters:
    return Filters(
        date_from=_parse_date(date_from),
        date_to=_parse_date(date_to),
        model=model or None,
        channel=channel if channel in ("telegram", "web") else None,
        include_test=bool(include_test),
    )


def _model_names(db: Session) -> list[str]:
    used = db.scalars(select(Dialog.model_version).distinct())
    return sorted(set(available_models()) | set(used))


def _download(content: bytes, filename: str, media_type: str) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content, media_type=media_type, headers=headers)


def _csv(table: list[list], filename: str) -> Response:
    buffer = StringIO()
    csv.writer(buffer, lineterminator="\r\n").writerows(table)
    # BOM boʻlmasa Excel oʻzbekcha belgilarni buzib koʻrsatadi.
    return _download(buffer.getvalue().encode("utf-8-sig"), filename, "text/csv; charset=utf-8")


def _xlsx(sheets: dict[str, list[list]], filename: str) -> Response:
    book = Workbook()
    book.remove(book.active)
    for title, table in sheets.items():
        sheet = book.create_sheet(title)
        for row in table:
            sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return _download(buffer.getvalue(), filename, _XLSX)


def _suffix(filters: Filters) -> str:
    return "_TEST" if filters.include_test else ""


@router.get("/analytics", response_class=HTMLResponse)
def analytics(
    request: Request, filters: Filters = Depends(parse_filters), db: Session = Depends(get_db)
):
    report = build_report(db, filters)
    return templates.TemplateResponse(
        request,
        "admin/analytics.html",
        {
            "report": report,
            "filters": filters,
            "models": _model_names(db),
            "query": request.url.query,
            "labels": LABELS,
            "levels": LEVELS,
            "chart": {"daily": report.daily, "categories": report.categories},
        },
    )


@router.get("/analytics/export.csv")
def export_csv(filters: Filters = Depends(parse_filters), db: Session = Depends(get_db)):
    return _csv(report_table(build_report(db, filters)), f"korsatkichlar{_suffix(filters)}.csv")


@router.get("/analytics/export.xlsx")
def export_xlsx(filters: Filters = Depends(parse_filters), db: Session = Depends(get_db)):
    report = build_report(db, filters)
    sheets = {
        "Koʻrsatkichlar": report_table(report),
        "Kunlik": daily_table(report),
        "Toifalar": categories_table(report),
    }
    return _xlsx(sheets, f"tahlil{_suffix(filters)}.xlsx")


def _ab_models(db: Session, model_a: str, model_b: str) -> tuple[str, str]:
    settings = load_settings(db)
    return model_a or settings.ab_model_a, model_b or settings.ab_model_b


@router.get("/analytics/ab", response_class=HTMLResponse)
def ab_page(
    request: Request,
    model_a: str = Query(""),
    model_b: str = Query(""),
    filters: Filters = Depends(parse_filters),
    db: Session = Depends(get_db),
):
    first, second = _ab_models(db, model_a, model_b)
    return templates.TemplateResponse(
        request,
        "admin/ab.html",
        {
            "report": asdict(build_ab(db, filters, first, second)),
            "filters": filters,
            "models": _model_names(db),
            "query": request.url.query,
        },
    )


@router.get("/analytics/ab/export.csv")
def ab_csv(
    model_a: str = Query(""),
    model_b: str = Query(""),
    filters: Filters = Depends(parse_filters),
    db: Session = Depends(get_db),
):
    first, second = _ab_models(db, model_a, model_b)
    return _csv(ab_table(build_ab(db, filters, first, second)), f"ab{_suffix(filters)}.csv")


@router.get("/analytics/ab/export.xlsx")
def ab_xlsx(
    model_a: str = Query(""),
    model_b: str = Query(""),
    filters: Filters = Depends(parse_filters),
    db: Session = Depends(get_db),
):
    first, second = _ab_models(db, model_a, model_b)
    table = ab_table(build_ab(db, filters, first, second))
    return _xlsx({"A-B": table}, f"ab{_suffix(filters)}.xlsx")
