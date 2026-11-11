import csv
import json
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.auth import create_or_update_staff
from app.db.models import AhpJudgment, Dialog, ExpertRating, Message, ModelVersion, Staff, User
from app.metrics.indicators import DialogStat, Filters, compute, load_stats
from app.metrics.report import build_ab, build_report
from tests.conftest import login_as

DAY = datetime(2026, 3, 10, 6, 0)


def hand_stats():
    return [
        DialogStat(
            resolved=True,
            csat=5,
            student_messages=2,
            latencies=[1000],
            sentiments=[0.5],
            expert_scores=[5],
        ),
        DialogStat(
            resolved=False,
            csat=3,
            handed_off=True,
            student_messages=4,
            had_fallback=True,
            latencies=[2000, 3000],
            sentiments=[-0.5],
            expert_scores=[3],
        ),
        DialogStat(student_messages=2, latencies=[2000], sentiments=[-0.2, -0.4]),
        DialogStat(resolved=True, student_messages=4),
    ]


def test_indicators_match_hand_calculation():
    result = compute(hand_stats(), 0.8)
    assert result["k1"] == 0.8
    assert result["k2"] == pytest.approx(0.75)
    assert result["k3"] == pytest.approx(0.75)
    assert result["k4"] == pytest.approx(2 / 3)
    assert result["k5"] == pytest.approx(0.75)
    assert result["k6"] == pytest.approx(2 / 3)
    assert result["k7"] == pytest.approx(0.6)
    assert result["k8"] == pytest.approx(0.75)
    assert result["kS"] == pytest.approx(0.5)


def test_no_dialogs_gives_no_values():
    assert set(compute([], 0.8).values()) == {None}


def test_slow_answers_floor_k7_at_zero():
    assert compute([DialogStat(student_messages=1, latencies=[9000])], None)["k7"] == 0


def test_few_turns_cap_k6_at_one():
    assert compute([DialogStat(student_messages=1)], None)["k6"] == 1


def add_dialog(
    db,
    channel="web",
    model="rule-based",
    started=DAY,
    ended=True,
    consent=True,
    is_test=False,
    resolved=None,
    csat=None,
    intent="Stipendiya",
):
    user = User(user_hash=f"h{db.query(User).count()}", channel=channel, consent=consent)
    db.add(user)
    db.flush()
    dialog = Dialog(
        user_id=user.id,
        channel=channel,
        model_version=model,
        started_at=started,
        ended_at=started + timedelta(minutes=5) if ended else None,
        is_test=is_test,
        resolved=resolved,
        csat=csat,
    )
    db.add(dialog)
    db.flush()
    db.add_all(
        [
            Message(
                dialog_id=dialog.id,
                sender="talaba",
                text_masked="savol",
                intent=intent,
                sentiment=0.0,
            ),
            Message(
                dialog_id=dialog.id,
                sender="bot",
                text_masked="javob",
                response_type="kb",
                latency_ms=500,
            ),
        ]
    )
    db.commit()
    return dialog


def test_only_ended_consented_real_dialogs_count(db_session):
    add_dialog(db_session)
    add_dialog(db_session, ended=False)
    add_dialog(db_session, consent=False)
    add_dialog(db_session, is_test=True)
    assert len(load_stats(db_session, Filters())) == 1
    assert len(load_stats(db_session, Filters(include_test=True))) == 2


def test_date_filter_uses_local_day(db_session):
    add_dialog(db_session, started=datetime(2026, 3, 10, 20, 0))  # 11-mart 01:00 Toshkentda
    assert load_stats(db_session, Filters(date_to=date(2026, 3, 10))) == []
    stats = load_stats(db_session, Filters(date_from=date(2026, 3, 11)))
    assert stats[0].local_date == date(2026, 3, 11)


def test_model_filter(db_session):
    add_dialog(db_session, model="svm")
    add_dialog(db_session)
    assert len(load_stats(db_session, Filters(model="svm"))) == 1


def test_stats_collect_messages_and_ratings(db_session):
    dialog = add_dialog(db_session)
    create_or_update_staff(db_session, "e", "parol-12345", "ekspert")
    staff = db_session.scalars(select(Staff)).one()
    db_session.add(ExpertRating(dialog_id=dialog.id, expert_id=staff.id, score=4))
    db_session.commit()
    stat = load_stats(db_session, Filters())[0]
    assert stat.student_messages == 1
    assert stat.latencies == [500]
    assert stat.category == "Stipendiya"
    assert stat.expert_scores == [4]


MATRICES = {
    0: [[1, 2, 4], [0.5, 1, 2], [0.25, 0.5, 1]],
    1: [[1, 1, 1], [1, 1, 1], [1, 1, 1]],
    2: [[1, 1, 1], [1, 1, 1], [1, 1, 1]],
    3: [[1, 1], [1, 1]],
}


def add_ahp(db, login="exp"):
    create_or_update_staff(db, login, "parol-12345", "ekspert")
    staff = db.scalars(select(Staff).where(Staff.login == login)).one()
    for level, matrix in MATRICES.items():
        db.add(AhpJudgment(expert_id=staff.id, level=level, matrix_json=json.dumps(matrix), cr=0))
    db.commit()
    return staff


def full_data(db):
    staff = add_ahp(db)
    db.add(ModelVersion(name="rule-based", type="rule", metrics_json='{"macro_f1": 0.8}'))
    for channel, csat in (("web", 5), ("telegram", 3)):
        dialog = add_dialog(db, channel=channel, resolved=True, csat=csat)
        db.add(ExpertRating(dialog_id=dialog.id, expert_id=staff.id, score=5))
    db.commit()


def row(report, code):
    return next(r for r in report.rows if r["code"] == code)


def test_report_computes_q_per_channel(db_session):
    full_data(db_session)
    report = build_report(db_session, Filters())
    assert report.missing == []
    total, telegram, web = row(report, "Q")["values"]
    assert telegram < total < web
    k8 = row(report, "k8")["values"]
    assert k8 == [pytest.approx(0.75), pytest.approx(0.5), pytest.approx(1.0)]
    assert row(report, "Q")["interpretations"][0] in ("aʼlo", "yaxshi")
    assert report.weights.experts == 1
    assert report.daily[0]["q"] == pytest.approx(total)


def test_report_explains_what_is_missing(db_session):
    add_dialog(db_session)
    report = build_report(db_session, Filters())
    assert row(report, "Q")["values"][0] is None
    assert "AHP vaznlari kiritilmagan" in report.missing
    assert any(item.startswith("k1") for item in report.missing)


def test_daily_series_fills_gap_days(db_session):
    add_dialog(db_session, started=DAY)
    add_dialog(db_session, started=DAY + timedelta(days=2))
    daily = build_report(db_session, Filters()).daily
    assert [d["dialogs"] for d in daily] == [1, 0, 1]


def test_categories_sorted_and_unknown_named(db_session):
    add_dialog(db_session, intent="Yotoqxona")
    add_dialog(db_session, intent="Stipendiya")
    add_dialog(db_session, intent="Stipendiya")
    add_dialog(db_session, intent=None)
    names = [c["category"] for c in build_report(db_session, Filters()).categories]
    assert names[0] == "Stipendiya"
    assert "Aniqlanmagan" in names


def test_ab_compares_two_models(db_session):
    add_ahp(db_session)
    for _ in range(30):
        add_dialog(db_session, model="rule-based", resolved=False, csat=2)
        add_dialog(db_session, model="svm", resolved=True, csat=5)
    report = build_ab(db_session, Filters(), "rule-based", "svm")
    assert (report.n_a, report.n_b) == (30, 30)
    assert report.k4_p < 0.05
    assert report.csat_p < 0.05
    k4 = next(r for r in report.rows if r["label"].startswith("k4"))
    assert (k4["a"], k4["b"]) == (0, 1)


def test_ab_without_data_has_no_p_values(db_session):
    report = build_ab(db_session, Filters(), "a", "b")
    assert report.k4_p is None
    assert report.csat_p is None


@pytest.mark.parametrize(
    "path",
    [
        "/admin/analytics",
        "/admin/analytics/ab",
        "/admin/analytics/export.csv",
        "/admin/analytics/ab/export.xlsx",
    ],
)
def test_pages_are_admin_only(client, db_session, path):
    assert client.get(path, follow_redirects=False).status_code == 303
    login_as(client, db_session, "op", "operator")
    assert client.get(path, follow_redirects=False).status_code == 403


def test_empty_panel_renders(admin_client):
    page = admin_client.get("/admin/analytics")
    assert page.status_code == 200
    assert "Tahlil paneli" in page.text
    assert admin_client.get("/admin/analytics/ab").status_code == 200


def test_panel_with_data_renders(admin_client, db_session):
    full_data(db_session)
    page = admin_client.get("/admin/analytics").text
    assert "Q — Integral indeks" in page
    assert 'id="quality"' in page
    assert "izchillik yetarli emas" not in page


def test_bad_query_values_are_ignored(admin_client):
    url = "/admin/analytics?date_from=abc&date_to=&model=&include_test="
    assert admin_client.get(url).status_code == 200


def test_test_data_warning(admin_client, db_session):
    add_dialog(db_session, is_test=True)
    assert "test dialoglari" not in admin_client.get("/admin/analytics").text
    page = admin_client.get("/admin/analytics?include_test=1").text
    assert "Bu raqamlarni dissertatsiyada ishlatmang" in page


def test_csv_export(admin_client, db_session):
    full_data(db_session)
    response = admin_client.get("/admin/analytics/export.csv")
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert 'filename="korsatkichlar.csv"' in response.headers["content-disposition"]
    rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == ["Koʻrsatkich", "Jami", "Telegram", "Veb"]
    assert any(r[0].startswith("Q ") and r[1] for r in rows)


def test_test_export_is_named(admin_client):
    response = admin_client.get("/admin/analytics/export.csv?include_test=1")
    assert "korsatkichlar_TEST.csv" in response.headers["content-disposition"]


def test_xlsx_export(admin_client, db_session):
    full_data(db_session)
    book = load_workbook(BytesIO(admin_client.get("/admin/analytics/export.xlsx").content))
    assert book.sheetnames == ["Koʻrsatkichlar", "Kunlik", "Toifalar"]
    assert book["Kunlik"]["B2"].value == 2


def test_ab_exports(admin_client, db_session):
    add_dialog(db_session, model="svm", resolved=True)
    query = "?model_a=rule-based&model_b=svm"
    text = admin_client.get(f"/admin/analytics/ab/export.csv{query}").content.decode("utf-8-sig")
    assert text.splitlines()[0] == "Koʻrsatkich,rule-based,svm"
    book = load_workbook(
        BytesIO(admin_client.get(f"/admin/analytics/ab/export.xlsx{query}").content)
    )
    assert book.sheetnames == ["A-B"]
