import json
from datetime import datetime, timedelta

from app.db.models import AhpJudgment, Handoff, KbItem, Staff
from app.metrics.dashboard import build_dashboard
from tests.test_analytics import add_dialog

NOW = datetime(2026, 12, 10, 9, 0)  # Toshkentda 14:00


def test_dashboard_counts_only_real_dialogs(db_session):
    add_dialog(
        db_session, started=NOW - timedelta(hours=1), resolved=True, csat=5, intent="Yotoqxona"
    )
    add_dialog(
        db_session, started=NOW - timedelta(days=2), resolved=False, csat=3, intent="Yotoqxona"
    )
    add_dialog(db_session, started=NOW - timedelta(days=30), intent="Stipendiya")
    add_dialog(db_session, started=NOW, is_test=True, resolved=True, csat=1)
    handed = add_dialog(db_session, started=NOW - timedelta(hours=2), consent=False)
    db_session.add(Handoff(dialog_id=handed.id))
    db_session.add_all(
        [
            KbItem(category="Stipendiya", intent="a", questions="q", answer="x", verified=True),
            KbItem(category="Stipendiya", intent="b", questions="q", answer="y", verified=False),
        ]
    )
    db_session.commit()

    d = build_dashboard(db_session, test_mode=False, now=NOW)

    assert d.dialogs_total == 4
    assert d.dialogs_today == 2
    assert d.students == 3  # rozilik bermagan foydalanuvchi sanalmaydi
    assert d.resolved_share == 0.5
    assert d.csat_avg == 4
    assert d.pending_handoffs == 1
    assert (d.kb_verified, d.kb_total) == (1, 2)
    assert d.ahp_done is False
    assert len(d.daily) == 14 and d.daily[-1]["dialogs"] == 2
    assert d.daily_max == 2
    assert d.categories[0] == {"name": "Yotoqxona", "dialogs": 2}
    assert d.last_message_at is not None


def test_dashboard_ahp_done(db_session):
    staff = Staff(login="e", password_hash="x", role="ekspert")
    db_session.add(staff)
    db_session.flush()
    for level in range(4):
        db_session.add(
            AhpJudgment(expert_id=staff.id, level=level, matrix_json=json.dumps([[1]]), cr=0)
        )
    db_session.commit()
    assert build_dashboard(db_session, test_mode=True, now=NOW).ahp_done is True


def test_dashboard_page(admin_client):
    page = admin_client.get("/admin")
    assert page.status_code == 200
    assert "Bosh sahifa" in page.text
    assert "Eʼtibor talab qiladi" in page.text
    assert "Grafik talabalar yoza boshlagach" in page.text
    assert 'href="https://t.me/buxdu_talababot"' in page.text
    assert page.text.count('data-tg="tg://resolve?domain=buxdu_talababot"') == 2


def test_operator_pages_show_tashkent_time(admin_client, db_session):
    dialog = add_dialog(db_session, started=datetime(2026, 12, 10, 10, 0))
    handoff = Handoff(dialog_id=dialog.id, created_at=datetime(2026, 12, 10, 10, 0))
    db_session.add(handoff)
    db_session.commit()
    assert "10.12.2026 15:00" in admin_client.get("/operator").text
    assert "Talaba · " in admin_client.get(f"/operator/{handoff.id}").text
