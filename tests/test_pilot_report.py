from datetime import datetime, timedelta

from docx import Document

from app.metrics.indicators import Filters
from scripts.pilot_report import Options, _fmt, _p_text, build_docx
from tests.test_analytics import DAY, add_dialog


def options(**filters) -> Options:
    return Options(
        filters=Filters(**filters),
        model_a="rule-based",
        model_b="svm",
        created=datetime(2026, 12, 1, 9, 0),
    )


def text_of(path) -> str:
    doc = Document(path)
    cells = [cell.text for table in doc.tables for row in table.rows for cell in row.cells]
    return "\n".join([p.text for p in doc.paragraphs] + cells)


def seed(db):
    for day in range(3):
        for model, resolved, csat in (("rule-based", False, 3), ("svm", True, 5)):
            add_dialog(
                db,
                model=model,
                started=DAY + timedelta(days=day),
                resolved=resolved,
                csat=csat,
                intent="Yotoqxona" if day else "Stipendiya",
            )


def test_report_has_all_sections(db_session, tmp_path):
    seed(db_session)
    path = build_docx(db_session, options(), tmp_path / "hisobot.docx")
    text = text_of(path)
    for heading in ("1. Umumiy", "2. Koʻrsatkichlar", "3. AHP", "4. Dinamika", "5. A/B"):
        assert heading in text
    assert "AHP soʻrovnomasi hali toʻldirilmagan" in text
    assert "A — rule-based (3 ta dialog); B — svm (3 ta dialog)." in text
    assert len(Document(path).inline_shapes) == 3  # kunlik, toifalar, A/B
    assert "DIQQAT" not in text


def test_test_dialogs_are_flagged(db_session, tmp_path):
    add_dialog(db_session, is_test=True)
    real = text_of(build_docx(db_session, options(), tmp_path / "a.docx"))
    test = text_of(build_docx(db_session, options(include_test=True), tmp_path / "b.docx"))
    assert "Tanlangan davrda dialoglar yoʻq." in real
    assert "DIQQAT: hisobotga test rejimidagi dialoglar ham kiritilgan" in test


def test_formatting_helpers():
    assert _fmt(None) == "—"
    assert _fmt(0.12345) == "0,123"
    assert _fmt(7) == "7"
    assert "hisoblanmadi" in _p_text(None, 0.05)
    assert "ahamiyatli (" in _p_text(0.01, 0.05)
    assert "ahamiyatli emas" in _p_text(0.5, 0.05)
