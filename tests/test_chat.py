from sqlalchemy import select

from app.db.models import Dialog, Handoff, KbItem, Message, User

URL = "/api/chat/message"
QUESTION = "Stipendiya qachon beriladi?"


def post(client, user="u1", **body):
    return client.post(URL, json={"channel": "web", "user_id": user, **body})


def consent(client, user="u1", action="consent_yes"):
    return post(client, user, action=action)


def add_kb(db, verified=True, source="Buxgalteriya"):
    db.add(
        KbItem(
            category="Stipendiya",
            intent="muddat",
            questions=f"{QUESTION}\nStipendiya kuni qaysi",
            answer="Har oyning 25-sanasida.",
            source=source,
            verified=verified,
        )
    )
    db.commit()


def test_first_contact_asks_consent_and_stores_no_message(client, db_session):
    data = post(client, text=QUESTION).json()
    assert "anonim saqlanadi" in data["text"]
    assert [b["action"] for b in data["buttons"]] == ["consent_yes", "consent_no"]
    assert db_session.scalars(select(Message)).all() == []


def test_consent_is_saved_either_way(client, db_session):
    consent(client, "a", "consent_yes")
    consent(client, "b", "consent_no")
    assert sorted(u.consent for u in db_session.scalars(select(User))) == [False, True]


def test_verified_answer_shows_source_and_logs(client, db_session):
    add_kb(db_session)
    consent(client)
    data = post(client, text=QUESTION).json()
    assert data["response_type"] == "kb"
    assert data["text"].endswith("Manba: Buxgalteriya")
    assert {b["action"] for b in data["buttons"]} == {"operator", "end"}

    bot, student = (
        db_session.scalars(select(Message).where(Message.sender == s)).one()
        for s in ("bot", "talaba")
    )
    assert student.text_masked == QUESTION
    assert bot.response_type == "kb"
    assert bot.latency_ms is not None
    dialog = db_session.get(Dialog, data["dialog_id"])
    assert dialog.is_test is True
    assert dialog.channel == "web"


def test_answer_shows_both_department_and_source(client, db_session):
    add_kb(db_session)
    item = db_session.scalars(select(KbItem)).one()
    item.department = "Registrator ofisi, 64-xona; +998 65 221-26-65"
    db_session.commit()
    consent(client)
    text = post(client, text=QUESTION).json()["text"]
    assert text == (
        "Har oyning 25-sanasida.\n\n"
        "Masʼul boʻlim: Registrator ofisi, 64-xona; +998 65 221-26-65\n"
        "Manba: Buxgalteriya"
    )


def test_answer_without_extras_is_plain(client, db_session):
    add_kb(db_session, source=None)
    consent(client)
    assert post(client, text=QUESTION).json()["text"] == "Har oyning 25-sanasida."


def test_unverified_answer_is_never_shown(client, db_session):
    add_kb(db_session, verified=False)
    consent(client)
    data = post(client, text=QUESTION).json()
    assert data["response_type"] == "clarify"
    assert "25-sanasida" not in data["text"]


def test_personal_data_is_masked_in_log(client, db_session):
    consent(client)
    post(client, text="raqamim +998901234567 pochta a@b.uz")
    student = db_session.scalars(select(Message).where(Message.sender == "talaba")).one()
    assert student.text_masked == "raqamim [TEL] pochta [EMAIL]"


def test_raw_user_id_is_not_stored(client, db_session):
    consent(client, "secret-user")
    user = db_session.scalars(select(User)).one()
    assert "secret-user" not in user.user_hash
    assert len(user.user_hash) == 64


def test_operator_creates_one_handoff(client, db_session):
    consent(client)
    first = post(client, action="operator").json()
    second = post(client, action="operator").json()
    assert first["response_type"] == "operator"
    assert first["dialog_id"] == second["dialog_id"]
    assert len(db_session.scalars(select(Handoff)).all()) == 1
    assert db_session.get(Dialog, first["dialog_id"]).handed_off is True


def test_end_closes_dialog_and_next_question_opens_new(client, db_session):
    consent(client)
    first = post(client, text="salom").json()
    ended = post(client, action="end").json()
    assert ended["dialog_id"] == first["dialog_id"]
    dialog = db_session.get(Dialog, first["dialog_id"])
    assert dialog.ended_at is not None
    assert dialog.end_reason == "user"
    assert post(client, text="yana").json()["dialog_id"] != first["dialog_id"]


def test_end_without_dialog(client):
    consent(client)
    data = post(client, action="end").json()
    assert data["dialog_id"] is None
    assert data["response_type"] == "system"


def test_telegram_channel_requires_internal_token(client):
    body = {"channel": "telegram", "user_id": "42", "action": "start"}
    assert client.post(URL, json=body).status_code == 403
    assert client.post(URL, json=body, headers={"X-Internal-Token": "wrong"}).status_code == 403
    ok = client.post(URL, json=body, headers={"X-Internal-Token": "test-bot-token"})
    assert ok.status_code == 200


def test_same_id_on_two_channels_is_two_users(client, db_session):
    post(client, "42", action="start")
    client.post(
        URL,
        json={"channel": "telegram", "user_id": "42", "action": "start"},
        headers={"X-Internal-Token": "test-bot-token"},
    )
    assert len(db_session.scalars(select(User)).all()) == 2


def test_request_needs_exactly_one_of_text_and_action(client):
    assert post(client).status_code == 422
    assert post(client, text="   ").status_code == 422
    assert post(client, text="a", action="end").status_code == 422


def test_chat_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Operator bilan bog" in response.text


def test_static_files_are_served(client):
    response = client.get("/static/README.txt")
    assert response.status_code == 200
    assert client.get("/static/yoq.png").status_code == 404


def test_models_are_warmed_up_at_startup(monkeypatch):
    import app.main as main

    loaded = []
    monkeypatch.setattr(main, "available_models", lambda: ["rule-based", "buzuq"])

    class Fake:
        def __init__(self, name):
            self.name = name

        def predict(self, _text):
            if self.name == "buzuq":
                raise RuntimeError("model fayli buzuq")
            loaded.append(self.name)

    monkeypatch.setattr(main, "get_classifier", Fake)
    main._warm_up_models()  # buzuq model ilovani toʻxtatmaydi
    assert loaded == ["rule-based"]


def test_verified_answer_carries_category_and_title(client, db_session):
    add_kb(db_session)
    consent(client)
    data = post(client, text=QUESTION).json()
    assert (data["category"], data["title"]) == ("Stipendiya", QUESTION)


def test_topic_button_answers_directly_and_logs_like_a_question(client, db_session):
    add_kb(db_session)
    consent(client)
    item = db_session.scalars(select(KbItem)).one()
    data = post(client, action=f"kb:{item.id}").json()
    assert data["response_type"] == "kb"
    assert data["text"].startswith("Har oyning 25-sanasida.")
    student = db_session.scalars(select(Message).where(Message.sender == "talaba")).one()
    assert (student.text_masked, student.intent, student.confidence) == (
        QUESTION,
        "Stipendiya",
        1.0,
    )


def test_unverified_or_missing_topic_is_refused(client, db_session):
    add_kb(db_session, verified=False)
    consent(client)
    item = db_session.scalars(select(KbItem)).one()
    for action in (f"kb:{item.id}", "kb:999"):
        data = post(client, action=action).json()
        assert data["response_type"] == "system"
    assert db_session.scalars(select(Message)).all() == []


def test_topic_while_waiting_for_operator_keeps_waiting(client, db_session):
    add_kb(db_session)
    consent(client)
    post(client, action="operator")
    item = db_session.scalars(select(KbItem)).one()
    data = post(client, action=f"kb:{item.id}").json()
    assert data["response_type"] == "operator"


def test_internal_topics_lists_only_verified(client, db_session):
    from app.config import get_settings

    add_kb(db_session)
    add_kb(db_session, verified=False)
    headers = {"X-Internal-Token": get_settings().bot_api_token}
    topics = client.get("/api/internal/topics?category=Stipendiya", headers=headers).json()
    assert [t["title"] for t in topics] == [QUESTION]
    assert client.get("/api/internal/topics?category=Yoq", headers=headers).status_code == 404
    assert client.get("/api/internal/topics?category=Stipendiya").status_code == 403
