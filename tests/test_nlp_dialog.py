from datetime import timedelta

from sqlalchemy import select

from app.db.models import Dialog, Handoff, KbItem, Message, Setting, SlangTerm, utcnow
from app.nlp import classifier
from app.nlp.train_svm import train

URL = "/api/chat/message"


def post(client, user="u1", **body):
    return client.post(URL, json={"channel": "web", "user_id": user, **body})


def start(client, db, user="u1"):
    post(client, user, action="consent_yes")
    db.add_all(
        [
            KbItem(
                category="Stipendiya",
                intent="muddat",
                questions="Stipendiya qachon beriladi\nIjtimoiy stipendiya qachon beriladi",
                answer="Har oyning 25-sanasida.",
                source="Buxgalteriya",
                verified=True,
            ),
            KbItem(
                category="Yotoqxona",
                intent="joy",
                questions="Yotoqxonaga qanday joylashaman",
                answer="Dekanatga ariza yozing.",
                verified=True,
            ),
        ]
    )
    db.commit()


def bot_messages(db):
    return db.scalars(select(Message).where(Message.sender == "bot")).all()


def student_messages(db):
    return db.scalars(select(Message).where(Message.sender == "talaba")).all()


def test_answer_logs_full_record(client, db_session):
    start(client, db_session)
    data = post(client, text="STIPENDIYA qachon beriladi???").json()
    assert data["response_type"] == "kb"
    student = student_messages(db_session)[0]
    assert student.text_masked == "STIPENDIYA qachon beriladi???"
    assert student.text_norm == "stipendiya qachon beriladi???"
    assert student.intent == "Stipendiya"
    assert student.confidence >= 0.6
    bot = bot_messages(db_session)[0]
    assert bot.intent == "Stipendiya"
    assert bot.latency_ms is not None
    assert db_session.get(Dialog, data["dialog_id"]).model_version == "rule-based"


def test_cyrillic_and_latin_get_same_answer(client, db_session):
    start(client, db_session)
    latin = post(client, text="Stipendiya qachon beriladi").json()
    cyrillic = post(client, text="Стипендия қачон берилади").json()
    assert latin["response_type"] == cyrillic["response_type"] == "kb"
    assert latin["text"] == cyrillic["text"]


def test_slang_from_database_is_applied(client, db_session):
    start(client, db_session)
    db_session.add(SlangTerm(term="stipuxa", replacement="stipendiya"))
    db_session.commit()
    assert post(client, text="stipuxa qachon beriladi").json()["response_type"] == "kb"


def test_name_is_masked_in_both_log_columns(client, db_session):
    start(client, db_session)
    post(client, text="Ismim Aziza, stipendiya qachon beriladi")
    student = student_messages(db_session)[0]
    assert "aziza" not in student.text_masked.lower()
    assert "aziza" not in student.text_norm


def test_clarify_then_fallback_hands_off(client, db_session):
    start(client, db_session)
    first = post(client, text="salom").json()
    assert first["response_type"] == "clarify"
    assert sum(b["action"].startswith("category:") for b in first["buttons"]) == 2

    second = post(client, text="qalaysiz").json()
    assert second["response_type"] == "fallback"
    assert "operatorga" in second["text"]
    assert len(db_session.scalars(select(Handoff)).all()) == 1
    assert db_session.get(Dialog, second["dialog_id"]).handed_off is True


def test_understood_answer_resets_miss_count(client, db_session):
    start(client, db_session)
    assert post(client, text="salom").json()["response_type"] == "clarify"
    assert post(client, text="Stipendiya qachon beriladi").json()["response_type"] == "kb"
    assert post(client, text="tushunarli emas endi bu").json()["response_type"] == "clarify"


def test_category_button_answers_original_question(client, db_session):
    start(client, db_session)
    post(client, text="qachon beriladi")
    data = post(client, action="category:Stipendiya").json()
    assert data["response_type"] == "kb"
    assert "25-sanasida" in data["text"]
    assert student_messages(db_session)[-1].text_masked == "Stipendiya"


def test_category_button_without_match_hands_off(client, db_session):
    start(client, db_session)
    post(client, text="salom")
    assert post(client, action="category:Boshqa").json()["response_type"] == "fallback"


def test_stale_category_button_without_dialog(client, db_session):
    start(client, db_session)
    data = post(client, action="category:Boshqa").json()
    assert data["response_type"] == "system"
    assert db_session.scalars(select(Dialog)).all() == []


def test_invalid_category_action_is_rejected(client):
    assert post(client, action="category:Xato").status_code == 422
    assert post(client, action="nimadir").status_code == 422


def test_typing_operator_hands_off(client, db_session):
    start(client, db_session)
    data = post(client, text="Operatorga ulang").json()
    assert data["response_type"] == "operator"
    assert len(db_session.scalars(select(Handoff)).all()) == 1
    assert student_messages(db_session)[0].text_norm == "operatorga ulang"


def test_follow_up_uses_recent_context(client, db_session):
    start(client, db_session)
    post(client, text="Stipendiya qachon beriladi")
    data = post(client, text="ijtimoiysi-chi?").json()
    assert data["response_type"] == "kb"
    assert "25-sanasida" in data["text"]


def test_follow_up_chain_keeps_context(client, db_session):
    start(client, db_session)
    post(client, text="Stipendiya qachon beriladi")
    post(client, text="ijtimoiysi-chi?")
    assert post(client, text="ijtimoiysi-chi?").json()["response_type"] == "kb"


def test_context_expires_after_ten_minutes(client, db_session):
    start(client, db_session)
    post(client, text="Stipendiya qachon beriladi")
    bot_messages(db_session)[0].created_at = utcnow() - timedelta(minutes=11)
    db_session.commit()
    assert post(client, text="ijtimoiysi-chi?").json()["response_type"] == "clarify"


def set_settings(db, **values):
    for key, value in values.items():
        db.merge(Setting(key=key, value=value))
    db.commit()


def test_tau_setting_is_respected(client, db_session):
    start(client, db_session)
    set_settings(db_session, tau="0.99")
    assert post(client, text="Stipendiya qachon beriladi").json()["response_type"] == "clarify"


def test_sigma_setting_is_respected(client, db_session):
    start(client, db_session)
    set_settings(db_session, sigma="1.01")
    assert post(client, text="Stipendiya kerak menga").json()["response_type"] == "clarify"


def trained_svm(monkeypatch, tmp_path):
    path = tmp_path / "svm.joblib"
    monkeypatch.setattr(classifier, "MODEL_PATH", path)
    texts = ["stipendiya qachon", "stipendiya miqdori", "stipendiya kartasi"]
    texts += ["yotoqxona joyi", "yotoqxona narxi", "yotoqxona kerak"]
    train(texts, ["Stipendiya"] * 3 + ["Yotoqxona"] * 3, path)


def test_active_svm_model_is_used(client, db_session, monkeypatch, tmp_path):
    trained_svm(monkeypatch, tmp_path)
    start(client, db_session)
    set_settings(db_session, active_model="svm", tau="0.1")
    data = post(client, text="Stipendiya qachon beriladi").json()
    assert db_session.get(Dialog, data["dialog_id"]).model_version == "svm"
    assert data["response_type"] == "kb"


def test_ab_assigns_both_models_and_keeps_them(client, db_session, monkeypatch, tmp_path):
    trained_svm(monkeypatch, tmp_path)
    start(client, db_session)
    set_settings(db_session, ab_enabled="True", ab_model_a="rule-based", ab_model_b="svm")
    versions = set()
    for number in range(30):
        user = f"ab{number}"
        post(client, user, action="consent_yes")
        first = post(client, user, text="salom").json()
        second = post(client, user, text="Stipendiya qachon beriladi").json()
        assert first["dialog_id"] == second["dialog_id"]
        versions.add(db_session.get(Dialog, first["dialog_id"]).model_version)
    assert versions == {"rule-based", "svm"}


def test_knowledge_base_edits_take_effect_immediately(client, db_session):
    start(client, db_session)
    assert "Bankka" not in post(client, text="Stipendiya kartasi yopildi").json()["text"]
    db_session.add(
        KbItem(
            category="Stipendiya",
            intent="karta",
            questions="Stipendiya kartasi yopildi",
            answer="Bankka boring.",
            verified=True,
        )
    )
    db_session.commit()
    post(client, action="end")
    assert "Bankka" in post(client, text="Stipendiya kartasi yopildi").json()["text"]

    item = db_session.scalars(select(KbItem).where(KbItem.intent == "karta")).one()
    item.verified = False
    db_session.commit()
    post(client, action="end")
    assert "Bankka" not in post(client, text="Stipendiya kartasi yopildi").json()["text"]
