"""Pilot natijalari boʻyicha Word hisobot (dissertatsiya 3.3 uchun jadval va grafiklar).

    python -m scripts.pilot_report --out hisobot.docx [--dan 2026-12-01] [--gacha 2026-12-21]
                                   [--kanal telegram|web] [--sinov]

Raqamlar admin paneldagi tahlil sahifasi bilan bir xil funksiyalardan olinadi
(app.metrics.report), shuning uchun ikkalasi har doim mos keladi.
--sinov: test rejimidagi dialoglar ham qoʻshiladi; hisobotda bu ochiq yoziladi.
"""

import argparse
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.table import WD_TABLE_ALIGNMENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.metrics.indicators import Filters  # noqa: E402
from app.metrics.integral import DIMENSIONS, LABELS, LEVELS, interpret  # noqa: E402
from app.metrics.report import AbReport, Report, build_ab, build_report  # noqa: E402
from app.settings_store import load_settings  # noqa: E402

FONT = "Times New Roman"
HEAD_FILL = "D9E2F3"
WARN = "C00000"
BLUE, ORANGE = "#2a78d6", "#e08a2c"
_PCT_CODES = ("k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "kS", "QD1", "QD2", "QD3", "Q")


@dataclass
class Options:
    filters: Filters
    model_a: str
    model_b: str
    created: datetime


def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}".replace(".", ",")
    return str(value)


def _period(filters: Filters) -> str:
    start = filters.date_from.isoformat() if filters.date_from else "boshidan"
    end = filters.date_to.isoformat() if filters.date_to else "bugungacha"
    return f"{start} — {end}"


# ---------- Word yordamchilari ----------


def _shade(cell, color: str) -> None:
    props = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    props.append(shd)


def _table(doc, header: list[str], rows: list[list], widths: list[float]) -> None:
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, text in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(text)
        run.bold = True
        run.font.size = Pt(11)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        _shade(cell, HEAD_FILL)
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(value))
            run.font.size = Pt(11)
            if i:
                cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    # Word va LibreOffice kenglikni faqat fixed layout + tblGrid + har bir katak bilan aniq oladi.
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    table._tbl.tblPr.append(layout)
    for i, grid_col in enumerate(table._tbl.tblGrid.findall(qn("w:gridCol"))):
        grid_col.set(qn("w:w"), str(int(Cm(widths[i]).twips)))
    for row in table.rows:
        for i, width in enumerate(widths):
            row.cells[i].width = Cm(width)
    doc.add_paragraph()


def _caption(doc, text: str) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.italic = True
    run.font.size = Pt(11)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _figure(doc, fig, caption: str) -> None:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    doc.add_picture(buffer, width=Cm(15.5))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    _caption(doc, caption)


def _note(doc, text: str, color: str | None = None, bold: bool = False) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


# ---------- grafiklar ----------


def _style_axes(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)


def _daily_figure(report: Report):
    days = [row["date"][5:] for row in report.daily]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.bar(days, [row["dialogs"] for row in report.daily], color=BLUE, label="Dialoglar")
    ax.set_ylabel("Dialoglar soni")
    _style_axes(ax)
    q_values = [row["q"] for row in report.daily]
    if any(value is not None for value in q_values):
        twin = ax.twinx()
        twin.plot(days, q_values, color=ORANGE, marker="o", label="Q")
        twin.set_ylim(0, 1)
        twin.set_ylabel("Integral indeks Q")
        twin.spines[["top"]].set_visible(False)
    ax.tick_params(axis="x", rotation=60, labelsize=8)
    return fig


def _categories_figure(report: Report):
    names = [row["category"] for row in report.categories][::-1]
    values = [row["dialogs"] for row in report.categories][::-1]
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(names) + 1))
    ax.barh(names, values, color=BLUE)
    for y, value in enumerate(values):
        ax.text(value, y, f" {value}", va="center", fontsize=9)
    ax.set_xlabel("Dialoglar soni")
    ax.spines[["top", "right"]].set_visible(False)
    return fig


def _ab_figure(ab: AbReport):
    codes = [c for c in ("k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "Q")]
    by_label = {row["label"]: row for row in ab.rows}
    a = [by_label[LABELS[c]]["a"] for c in codes]
    b = [by_label[LABELS[c]]["b"] for c in codes]
    x = range(len(codes))
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.bar([i - 0.2 for i in x], [v or 0 for v in a], 0.4, color=BLUE, label=f"A: {ab.model_a}")
    ax.bar([i + 0.2 for i in x], [v or 0 for v in b], 0.4, color=ORANGE, label=f"B: {ab.model_b}")
    ax.set_xticks(list(x), codes)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Qiymat (0–1)")
    ax.legend(frameon=False)
    _style_axes(ax)
    return fig


# ---------- hisobot ----------


def _p_text(p: float | None, alpha: float) -> str:
    if p is None:
        return "hisoblanmadi (maʼlumot yetarli emas)"
    verdict = "farq statistik ahamiyatli" if p < alpha else "farq statistik ahamiyatli emas"
    return f"p = {_fmt(p, 4)} — {verdict} (α = {_fmt(alpha, 2)})"


def build_docx(db: Session, options: Options, out: Path) -> Path:
    filters = options.filters
    report = build_report(db, filters)
    ab = build_ab(db, filters, options.model_a, options.model_b)

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(12)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    for name, size in (("Title", 18), ("Heading 1", 14), ("Heading 2", 13)):
        style = doc.styles[name]
        style.font.name = FONT
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
        style.paragraph_format.keep_with_next = True
    section = doc.sections[0]
    section.left_margin, section.right_margin = Cm(2.5), Cm(1.5)
    section.top_margin = section.bottom_margin = Cm(2)

    doc.add_heading("TalabaBot pilot natijalari", 0)
    _note(doc, f"Davr: {_period(filters)}")
    _note(doc, f"Kanal: {filters.channel or 'barcha (Telegram va veb)'}")
    _note(doc, f"Hisobot yaratilgan: {options.created:%Y-%m-%d %H:%M}")
    if filters.include_test:
        _note(
            doc,
            "DIQQAT: hisobotga test rejimidagi dialoglar ham kiritilgan. "
            "Bu raqamlar pilot natijasi emas va dissertatsiyada ishlatilmaydi.",
            WARN,
            bold=True,
        )
    if report.missing:
        _note(doc, "Hisoblanmagan qismlar: " + "; ".join(report.missing) + ".", WARN)

    # 1. Umumiy maʼlumot
    doc.add_heading("1. Umumiy maʼlumot", 1)
    rows = [[row["label"], *row["values"]] for row in report.counts]
    _table(doc, ["", *report.columns], rows, [7, 3, 3, 3])
    _caption(doc, "1-jadval. Pilot davridagi dialoglar soni")

    # 2. Koʻrsatkichlar
    doc.add_heading("2. Koʻrsatkichlar va integral indeks", 1)
    rows = []
    for row in report.rows:
        values = [_fmt(v) for v in row["values"]]
        interp = row["interpretations"][0]
        rows.append([row["label"], *values, interp or ""])
    _table(doc, ["Koʻrsatkich", *report.columns, "Talqin (jami)"], rows, [6, 2.4, 2.4, 2.4, 2.6])
    _caption(doc, "2-jadval. k1–k8, kS, qisman indekslar QD1–QD3 va integral indeks Q")
    _note(
        doc,
        "Talqin shkalasi: Q ≥ 0,85 — aʼlo; 0,70–0,85 — yaxshi; 0,50–0,70 — qoniqarli; "
        "Q < 0,50 — past (TZ 4.8.1).",
    )

    # 3. AHP vaznlari
    doc.add_heading("3. AHP vaznlari", 1)
    if report.weights is None:
        _note(doc, "AHP soʻrovnomasi hali toʻldirilmagan, shuning uchun Q hisoblanmadi.", WARN)
    else:
        w = report.weights
        rows = []
        for dim in LEVELS[0]:
            rows.append([f"{dim} (oʻlcham)", _fmt(w.dimensions[dim]), "", ""])
            for code in DIMENSIONS[dim]:
                rows.append(["    " + LABELS[code], "", _fmt(w.local[code]), _fmt(w.overall(code))])
        _table(doc, ["Mezon", "Wj", "vi", "wi = Wj·vi"], rows, [8, 2.5, 2.5, 3])
        _caption(doc, "3-jadval. AHP vaznlari")
        cr = "; ".join(f"{_fmt(value, 3)}" for _, value in sorted(w.consistency.items()))
        bad = [v for v in w.consistency.values() if v >= 0.10]
        _note(
            doc, f"Ekspertlar soni: {w.experts}. Izchillik nisbati CR (darajalar boʻyicha): {cr}."
        )
        if bad:
            _note(doc, "Baʼzi matritsalarda CR ≥ 0,10: baholarni qayta koʻrib chiqish kerak.", WARN)

    # 4. Grafiklar
    doc.add_heading("4. Dinamika va toifalar", 1)
    if report.daily:
        _figure(doc, _daily_figure(report), "1-rasm. Kunlik dialoglar soni va Q dinamikasi")
    if report.categories:
        _figure(
            doc, _categories_figure(report), "2-rasm. Murojaatlarning toifalar boʻyicha taqsimoti"
        )
        rows = [[row["category"], row["dialogs"]] for row in report.categories]
        _table(doc, ["Toifa", "Dialoglar"], rows, [9, 4])
        _caption(doc, "4-jadval. Toifalar boʻyicha taqsimot")
    if not report.daily:
        _note(doc, "Tanlangan davrda dialoglar yoʻq.", WARN)

    # 5. A/B
    doc.add_heading("5. A/B taqqoslash", 1)
    _note(doc, f"A — {ab.model_a} ({ab.n_a} ta dialog); B — {ab.model_b} ({ab.n_b} ta dialog).")
    rows = [[row["label"], _fmt(row["a"]), _fmt(row["b"])] for row in ab.rows]
    _table(doc, ["Koʻrsatkich", f"A: {ab.model_a}", f"B: {ab.model_b}"], rows, [8, 4, 4])
    _caption(doc, "5-jadval. Modellar boʻyicha koʻrsatkichlar")
    if ab.n_a and ab.n_b:
        _figure(doc, _ab_figure(ab), "3-rasm. A va B versiyalar koʻrsatkichlari")
    _note(doc, "k4 (vazifa bajarilishi), χ² mezoni: " + _p_text(ab.k4_p, ab.alpha))
    _note(doc, "CSAT (qoniqish), Mann–Whitney mezoni: " + _p_text(ab.csat_p, ab.alpha))
    q_a = next(r["a"] for r in ab.rows if r["label"] == LABELS["Q"])
    q_b = next(r["b"] for r in ab.rows if r["label"] == LABELS["Q"])
    if q_a is not None and q_b is not None:
        _note(
            doc,
            f"Integral indeks: A — {_fmt(q_a)} ({interpret(q_a)}), "
            f"B — {_fmt(q_b)} ({interpret(q_b)}).",
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dan", type=date.fromisoformat)
    parser.add_argument("--gacha", type=date.fromisoformat)
    parser.add_argument("--kanal", choices=("telegram", "web"))
    parser.add_argument("--sinov", action="store_true", help="test dialoglarini ham qoʻshish")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        settings = load_settings(db)
        options = Options(
            filters=Filters(
                date_from=args.dan,
                date_to=args.gacha,
                channel=args.kanal,
                include_test=args.sinov,
            ),
            model_a=settings.ab_model_a,
            model_b=settings.ab_model_b,
            created=datetime.now(),
        )
        path = build_docx(db, options, args.out)
    print(f"Hisobot tayyor: {path}")


if __name__ == "__main__":
    main()
