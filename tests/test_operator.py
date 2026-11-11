from sqlalchemy import select

from app.db.models import Dialog, Handoff, Message, Staff, User
from app.security import decrypt, hash_password, verify_password
from tests.conftest import login_as

URL = "/api/chat/message"
TOKEN = {"X-Internal-Token": "test-bot-token"}


def web(client, user="w1", **body):
    return client.post(URL, json={"channel": "web", "user_id": user, **body})


def telegram(client, user="555", **body):
    return client.post(URL, json={"channel": "telegram", "user_id": user, **body}, headers=TOKEN)


def hand_off(send, client):
    send(client, action="consent_yes")
    send(client, text="Stipendiyam kelmadi")
    send(client, text="operator kerak")


def handoff_id(db):
    return db.scalars(select(Handoff)).one().id


def test_password_is_hashed_and_verifiable():
    stored = hash_password("maxfiy-parol")
    assert "maxfiy-parol" not in stored
    assert verify_password("maxfiy-parol", stored)
    assert not verify_password("boshqa", stored)
    assert hash_password("maxfiy-parol") != stored


def test_staff_password_is_not_stored_plain(admin_client, db_session):
    staff = db_session.scalars(select(Staff)).one()
    assert staff.password_hash.startswith("scrypt$")


def test_operator_cannot_open_admin(operator_client):
    assert operator_client.get("/admin/kb", follow_redirects=False).status_code == 403


def test_operator_login_lands_on_queue(client, db_session):
    from app.auth import create_or_update_staff

    create_or_update_staff(db_session, "op", "parol-12345", "operator")
    response = client.post(
        "/admin/login", data={"login": "op", "password": "parol-12345"}, follow_redirects=False
    )
    assert response.headers["location"] == "/operator"


def test_expert_cannot_open_operator(client, db_session):
    login_as(client, db_session, "exp", "ekspert")
    assert client.get("/operator", follow_redirects=False).status_code == 403


def test_deleted_staff_loses_access(operator_client, db_session):
    db_session.delete(db_session.scalars(select(Staff)).one())
    db_session.commit()
    assert operator_client.get("/operator", follow_redirects=False).status_code == 303


def test_anonymous_redirected(client):
    assert client.get("/operator", follow_redirects=False).status_code == 303
    assert client.post("/operator/1/reply", follow_redirects=False).status_code == 303


def test_queue_shows_time_category_and_history(operator_client, db_session):
    hand_off(web, operator_client)
    page = operator_client.get("/operator").text
    assert "Stipendiya" in page
    assert "web" in page
    detail = operator_client.get(f"/operator/{handoff_id(db_session)}").text
    assert "Stipendiyam kelmadi" in detail


def test_admin_can_also_use_queue(admin_client):
    assert admin_client.get("/operator").status_code == 200


def test_reply_reaches_web_with_full_text_and_masked_log(operator_client, db_session):
    hand_off(web, operator_client)
    reply = "Buxgalteriyaga qoʻngʻiroq qiling: +998901234567"
    operator_client.post(f"/operator/{handoff_id(db_session)}/reply", data={"text": reply})

    handoff = db_session.scalars(select(Handoff)).one()
    assert handoff.status == "answered"
    assert handoff.operator_id is not None
    assert handoff.answered_at is not None
    dialog = db_session.get(Dialog, handoff.dialog_id)
    assert dialog.end_reason == "operator"

    updates = operator_client.post("/api/chat/updates", json={"user_id": "w1"}).json()
    assert updates[0]["text"] == reply
    assert "hal boʻldimi" in updates[1]["text"]
    assert len(updates[1]["buttons"]) == 2

    stored = db_session.scalars(select(Message).where(Message.sender == "operator")).one()
    assert "901234567" not in stored.text_masked
    assert stored.outbox_text is None
    assert operator_client.post("/api/chat/updates", json={"user_id": "w1"}).json() == []


def test_reply_reaches_telegram_via_internal_api(operator_client, db_session):
    hand_off(telegram, operator_client)
    operator_client.post(f"/operator/{handoff_id(db_session)}/reply", data={"text": "Javob"})

    items = operator_client.get("/api/internal/pending", headers=TOKEN).json()
    assert [item["chat_id"] for item in items] == ["555", "555"]
    assert items[0]["text"] == "Javob"

    operator_client.post(f"/api/internal/messages/{items[0]['id']}/delivered", headers=TOKEN)
    remaining = operator_client.get("/api/internal/pending", headers=TOKEN).json()
    assert [item["id"] for item in remaining] == [items[1]["id"]]


def test_web_messages_do_not_leak_to_telegram_queue(operator_client, db_session):
    hand_off(web, operator_client)
    operator_client.post(f"/operator/{handoff_id(db_session)}/reply", data={"text": "Javob"})
    assert operator_client.get("/api/internal/pending", headers=TOKEN).json() == []


def test_one_web_user_cannot_take_anothers_updates(operator_client, db_session):
    hand_off(web, operator_client)
    operator_client.post(f"/operator/{handoff_id(db_session)}/reply", data={"text": "Javob"})
    assert operator_client.post("/api/chat/updates", json={"user_id": "other"}).json() == []


def test_chat_id_is_encrypted(client, db_session):
    telegram(client, "777", action="consent_yes")
    user = db_session.scalars(select(User)).one()
    assert "777" not in user.delivery_ref
    assert decrypt(user.delivery_ref) == "777"


def test_web_user_has_no_delivery_ref(client, db_session):
    web(client, action="consent_yes")
    assert db_session.scalars(select(User)).one().delivery_ref is None


def test_internal_api_requires_token(client):
    assert client.get("/api/internal/pending").status_code == 403
    assert client.post("/api/internal/messages/1/delivered").status_code == 403


def test_ack_missing_message(client):
    assert client.post("/api/internal/messages/999/delivered", headers=TOKEN).status_code == 404


def test_empty_or_too_long_reply_is_refused(operator_client, db_session):
    hand_off(web, operator_client)
    identifier = handoff_id(db_session)
    operator_client.post(f"/operator/{identifier}/reply", data={"text": "   "})
    operator_client.post(f"/operator/{identifier}/reply", data={"text": "x" * 2001})
    assert db_session.scalars(select(Handoff)).one().status == "pending"


def test_second_reply_is_ignored(operator_client, db_session):
    hand_off(web, operator_client)
    identifier = handoff_id(db_session)
    operator_client.post(f"/operator/{identifier}/reply", data={"text": "Birinchi"})
    operator_client.post(f"/operator/{identifier}/reply", data={"text": "Ikkinchi"})
    assert len(db_session.scalars(select(Message).where(Message.sender == "operator")).all()) == 1


def test_missing_handoff_returns_404(operator_client):
    assert operator_client.get("/operator/999").status_code == 404
