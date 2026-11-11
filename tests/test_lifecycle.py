from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import Dialog, Handoff, Message, utcnow
from app.dialog import close_inactive_dialogs

URL = "/api/chat/message"


def post(client, user="u1", **body):
    return client.post(URL, json={"channel": "web", "user_id": user, **body})


def ready(client, user="u1"):
    post(client, user, action="consent_yes")


def opened(client, user="u1"):
    ready(client, user)
    return post(client, user, text="salom").json()["dialog_id"]


def test_end_asks_resolved_then_rating(client, db_session):
    dialog_id = opened(client)
    end = post(client, action="end").json()
    assert "hal boʻldimi" in end["text"]
    assert [b["action"] for b in end["buttons"]] == [
        f"resolved:{dialog_id}:yes",
        f"resolved:{dialog_id}:no",
    ]

    rate = post(client, action=f"resolved:{dialog_id}:yes").json()
    assert "1 dan 5 gacha" in rate["text"]
    assert len(rate["buttons"]) == 5

    done = post(client, action=f"rate:{dialog_id}:4").json()
    assert done["buttons"] == []
    dialog = db_session.get(Dialog, dialog_id)
    assert dialog.resolved is True
    assert dialog.csat == 4


def test_rating_is_optional(client, db_session):
    dialog_id = opened(client)
    post(client, action="end")
    assert post(client, text="yana savol").json()["dialog_id"] != dialog_id
    dialog = db_session.get(Dialog, dialog_id)
    assert dialog.resolved is None
    assert dialog.csat is None


def test_first_answer_wins(client, db_session):
    dialog_id = opened(client)
    post(client, action="end")
    post(client, action=f"resolved:{dialog_id}:no")
    post(client, action=f"resolved:{dialog_id}:yes")
    post(client, action=f"rate:{dialog_id}:2")
    post(client, action=f"rate:{dialog_id}:5")
    dialog = db_session.get(Dialog, dialog_id)
    assert dialog.resolved is False
    assert dialog.csat == 2


def test_cannot_rate_someone_elses_dialog(client, db_session):
    dialog_id = opened(client, "owner")
    post(client, "owner", action="end")
    ready(client, "intruder")
    post(client, "intruder", action=f"rate:{dialog_id}:1")
    assert db_session.get(Dialog, dialog_id).csat is None


def test_cannot_rate_open_dialog(client, db_session):
    dialog_id = opened(client)
    post(client, action=f"rate:{dialog_id}:5")
    assert db_session.get(Dialog, dialog_id).csat is None


@pytest.mark.parametrize("action", ["rate:1:6", "rate:1:0", "resolved:1:maybe", "rate:x:1"])
def test_invalid_feedback_action(client, action):
    assert post(client, action=action).status_code == 422


@pytest.mark.parametrize("text", ["rahmat", "Rahmaaat!", "katta rahmat", "Рахмат", "xayr"])
def test_closing_message_ends_dialog(client, db_session, text):
    dialog_id = opened(client)
    data = post(client, text=text).json()
    assert "hal boʻldimi" in data["text"]
    dialog = db_session.get(Dialog, dialog_id)
    assert dialog.ended_at is not None
    assert dialog.end_reason == "closing"


@pytest.mark.parametrize("text", ["rahmat, stipendiya qachon", "rahmat lekin tushunmadim"])
def test_thanks_inside_question_does_not_end(client, db_session, text):
    dialog_id = opened(client)
    post(client, text=text)
    assert db_session.get(Dialog, dialog_id).ended_at is None


def test_thanks_without_dialog_opens_nothing(client, db_session):
    ready(client)
    assert post(client, text="rahmat").json()["dialog_id"] is None
    assert db_session.scalars(select(Dialog)).all() == []


def test_sentiment_is_logged_for_student(client, db_session):
    ready(client)
    post(client, text="bu juda yomon")
    student = db_session.scalars(select(Message).where(Message.sender == "talaba")).one()
    assert student.sentiment < -0.25


def age(db, dialog_id, minutes):
    past = utcnow() - timedelta(minutes=minutes)
    for message in db.scalars(select(Message).where(Message.dialog_id == dialog_id)):
        message.created_at = past
    db.commit()


def test_inactive_dialog_is_closed_and_prompted(client, db_session):
    dialog_id = opened(client)
    age(db_session, dialog_id, 11)
    assert close_inactive_dialogs(db_session) == 1
    dialog = db_session.get(Dialog, dialog_id)
    assert dialog.end_reason == "timeout"
    prompt = db_session.scalars(select(Message).where(Message.delivered_at.is_(None))).all()
    assert "hal boʻldimi" in prompt[-1].text_masked
    assert close_inactive_dialogs(db_session) == 0


def test_recent_dialog_stays_open(client, db_session):
    dialog_id = opened(client)
    age(db_session, dialog_id, 9)
    assert close_inactive_dialogs(db_session) == 0


def test_waiting_for_operator_is_not_timed_out(client, db_session):
    ready(client)
    dialog_id = post(client, action="operator").json()["dialog_id"]
    age(db_session, dialog_id, 60)
    assert close_inactive_dialogs(db_session) == 0


def test_student_text_while_waiting_goes_to_history(client, db_session):
    ready(client)
    dialog_id = post(client, action="operator").json()["dialog_id"]
    data = post(client, text="tezroq iltimos").json()
    assert data["dialog_id"] == dialog_id
    assert "operatorda" in data["text"]
    student = db_session.scalars(select(Message).where(Message.sender == "talaba")).one()
    assert student.text_norm == "tezroq iltimos"


def test_thanks_while_waiting_does_not_cancel(client, db_session):
    ready(client)
    dialog_id = post(client, action="operator").json()["dialog_id"]
    post(client, text="rahmat")
    assert db_session.get(Dialog, dialog_id).ended_at is None


def test_end_while_waiting_cancels_handoff(client, db_session):
    ready(client)
    post(client, action="operator")
    post(client, action="end")
    assert db_session.scalars(select(Handoff)).one().status == "cancelled"
