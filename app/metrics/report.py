"""Tahlil paneli va eksport uchun jadvallar (FR-26, FR-27, FR-29)."""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.kb_import import CATEGORIES
from app.metrics.ab_test import ALPHA, chi_square, mann_whitney
from app.metrics.indicators import DialogStat, Filters, compute, k2_from, load_stats, model_k1
from app.metrics.integral import LABELS, Weights, integral, interpret, load_weights
from app.settings_store import load_settings

COLUMNS = (("Jami", None), ("Telegram", "telegram"), ("Veb", "web"))
ROW_CODES = ("k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "kS", "QD1", "QD2", "QD3", "Q")
_INTERPRETED = ("QD1", "QD2", "QD3", "Q")
_DIGITS = 4
UNKNOWN_CATEGORY = "Aniqlanmagan"


@dataclass
class Report:
    columns: list[str]
    rows: list[dict]
    counts: list[dict]
    missing: list[str]
    weights: Weights | None
    daily: list[dict]
    categories: list[dict]


def _full_values(stats: list[DialogStat], k1, weights, **overrides) -> dict:
    values = compute(stats, k1, **overrides)
    return values | integral(values, weights)


def _counts(stats: list[DialogStat]) -> dict[str, int]:
    return {
        "N": len(stats),
        "k4": sum(stat.resolved is not None for stat in stats),
        "k8": sum(stat.csat is not None for stat in stats),
    }


def _daily(stats: list[DialogStat], k1, weights) -> list[dict]:
    if not stats:
        return []
    by_day: dict[date, list[DialogStat]] = {}
    for stat in stats:
        by_day.setdefault(stat.local_date, []).append(stat)
    # k1 va k2 kunlik emas: butun davr qiymati ishlatiladi.
    k2 = k2_from(stats)
    day, last, rows = min(by_day), max(by_day), []
    while day <= last:
        subset = by_day.get(day, [])
        q = _full_values(subset, k1, weights, k2=k2)["Q"] if subset else None
        rows.append({"date": day.isoformat(), "dialogs": len(subset), "q": q})
        day += timedelta(days=1)
    return rows


def _categories(stats: list[DialogStat]) -> list[dict]:
    counts = Counter(stat.category or UNKNOWN_CATEGORY for stat in stats)
    ordered = [name for name in (*CATEGORIES, UNKNOWN_CATEGORY) if counts[name]]
    ordered.sort(key=lambda name: -counts[name])
    return [{"category": name, "dialogs": counts[name]} for name in ordered]


def _missing(values: dict, weights: Weights | None) -> list[str]:
    reasons = [] if weights else ["AHP vaznlari kiritilmagan"]
    reasons += [
        LABELS[code]
        for code in ROW_CODES
        if code in values and values[code] is None and not code.startswith("Q")
    ]
    return reasons


def build_report(db: Session, filters: Filters) -> Report:
    stats = load_stats(db, replace(filters, channel=None))
    weights = load_weights(db)
    k1 = model_k1(db, filters.model or load_settings(db).active_model)

    subsets = [
        [stat for stat in stats if channel is None or stat.channel == channel]
        for _, channel in COLUMNS
    ]
    results = [_full_values(subset, k1, weights) for subset in subsets]
    rows = [
        {
            "code": code,
            "label": LABELS[code],
            "values": [result[code] for result in results],
            "interpretations": [
                interpret(result[code]) if code in _INTERPRETED else None for result in results
            ],
        }
        for code in ROW_CODES
    ]
    counts_by_column = [_counts(subset) for subset in subsets]
    counts = [
        {"label": label, "values": [c[key] for c in counts_by_column]}
        for label, key in (
            ("Dialoglar soni (N)", "N"),
            ("“Hal boʻldimi?” javoblari", "k4"),
            ("Baho qoʻyilgan dialoglar", "k8"),
        )
    ]
    return Report(
        columns=[name for name, _ in COLUMNS],
        rows=rows,
        counts=counts,
        missing=_missing(results[0], weights),
        weights=weights,
        daily=_daily(stats, k1, weights),
        categories=_categories(stats),
    )


def _round(value):
    return round(value, _DIGITS) if isinstance(value, float) else value


def report_table(report: Report) -> list[list]:
    header = ["Koʻrsatkich", *report.columns]
    body = [[row["label"], *map(_round, row["values"])] for row in report.rows]
    body += [[row["label"], *row["values"]] for row in report.counts]
    return [header, *body]


def daily_table(report: Report) -> list[list]:
    rows = [[row["date"], row["dialogs"], _round(row["q"])] for row in report.daily]
    return [["Sana", "Dialoglar", "Q"], *rows]


def categories_table(report: Report) -> list[list]:
    return [["Toifa", "Dialoglar"], *([r["category"], r["dialogs"]] for r in report.categories)]


@dataclass
class AbReport:
    model_a: str
    model_b: str
    rows: list[dict]
    n_a: int
    n_b: int
    k4_p: float | None
    csat_p: float | None
    alpha: float = ALPHA


def build_ab(db: Session, filters: Filters, model_a: str, model_b: str) -> AbReport:
    weights = load_weights(db)
    stats_a = load_stats(db, replace(filters, model=model_a))
    stats_b = load_stats(db, replace(filters, model=model_b))
    values_a = _full_values(stats_a, model_k1(db, model_a), weights)
    values_b = _full_values(stats_b, model_k1(db, model_b), weights)

    def resolved(stats: list[DialogStat], flag: bool) -> int:
        return sum(stat.resolved is flag for stat in stats)

    def csat(stats: list[DialogStat]) -> list[int]:
        return [stat.csat for stat in stats if stat.csat is not None]

    return AbReport(
        model_a=model_a,
        model_b=model_b,
        rows=[
            {"label": LABELS[code], "a": values_a[code], "b": values_b[code]} for code in ROW_CODES
        ],
        n_a=len(stats_a),
        n_b=len(stats_b),
        k4_p=chi_square(
            resolved(stats_a, True),
            resolved(stats_a, False),
            resolved(stats_b, True),
            resolved(stats_b, False),
        ),
        csat_p=mann_whitney(csat(stats_a), csat(stats_b)),
    )


def ab_table(report: AbReport) -> list[list]:
    body = [[row["label"], _round(row["a"]), _round(row["b"])] for row in report.rows]
    body.append(["Dialoglar soni (N)", report.n_a, report.n_b])
    body.append(["k4 farqi, χ² mezoni, p", _round(report.k4_p), ""])
    body.append(["CSAT farqi, Mann–Whitney mezoni, p", _round(report.csat_p), ""])
    return [["Koʻrsatkich", report.model_a, report.model_b], *body]
