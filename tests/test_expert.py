import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.api.expert import RATING_TARGET
from app.db.models import AhpJudgment, Dialog, ExpertRating, Message, User, utcnow
from app.metrics.integral import load_weights
from tests.conftest import login_as


def add_dialog(db, is_test=True, ended=True, consent=True, text="Savol matni"):
    user = User(user_hash=f"h{db.query(User).count()}", channel="web", consent=consent)
    db.add(user)
    db.flush()
    dialog = Dialog(
        user_id=user.id,
        channel="web",
        model_version="rule-based",
        ended_at=utcnow() - timedelta(minutes=1) if ended else None,
        is_test=is_test,
    )
    db.add(dialog)
    db.flush()
    db.add(Message(dialog_id=dialog.id, sender="talaba", text_masked=text))
    db.commit()
    return dialog


@pytest.fixture
def expert_client(client, db_session):
    return login_as(client, db_session, "exp", "ekspert")


def form(values=None):
    """Hamma juftlik "1"; values bilan alohida maydonlar almashtiriladi."""
    data = {}
    for level, size in ((0, 3), (1, 3), (2, 3), (3, 2)):
        for i in range(size):
            for j in range(i + 1, size):
                data[f"m{level}_{i}_{j}"] = "1"
    return data | (values or {})


@pytest.mark.parametrize("path", ["/expert", "/expert/ahp"])
def test_requires_expert(client, db_session, path):
    assert client.get(path, follow_redirects=False).status_code == 303
    login_as(client, db_session, "op", "operator")
    assert client.get(path, follow_redirects=False).status_code == 403


def test_expert_login_lands_on_rating(client, db_session):
    from app.auth import create_or_update_staff

    create_or_update_staff(db_session, "e2", "parol-12345", "ekspert")
    response = client.post(
        "/admin/login", data={"login": "e2", "password": "parol-12345"}, follow_redirects=False
    )
    assert response.headers["location"] == "/expert"


def test_page_shows_dialog_text(expert_client, db_session):
    add_dialog(db_session)
    assert "Savol matni" in expert_client.get("/expert").text


def test_rating_is_saved_once(expert_client, db_session):
    dialog = add_dialog(db_session)
    expert_client.post(f"/expert/rate/{dialog.id}", data={"score": "4"})
    expert_client.post(f"/expert/rate/{dialog.id}", data={"score": "1"})
    rating = db_session.scalars(select(ExpertRating)).one()
    assert rating.score == 4


def test_rated_dialog_is_not_shown_again(expert_client, db_session):
    dialog = add_dialog(db_session)
    expert_client.post(f"/expert/rate/{dialog.id}", data={"score": "4"})
    assert "baholanadigan dialog qolmadi" in expert_client.get("/expert").text


def test_two_experts_rate_same_dialog(expert_client, client, db_session):
    dialog = add_dialog(db_session)
    expert_client.post(f"/expert/rate/{dialog.id}", data={"score": "4"})
    login_as(client, db_session, "exp2", "ekspert")
    client.post(f"/expert/rate/{dialog.id}", data={"score": "2"})
    assert len(db_session.scalars(select(ExpertRating)).all()) == 2


@pytest.mark.parametrize("score", ["0", "6"])
def test_score_out_of_range(expert_client, db_session, score):
    dialog = add_dialog(db_session)
    assert expert_client.post(f"/expert/rate/{dialog.id}", data={"score": score}).status_code == 400


@pytest.mark.parametrize("kwargs", [{"ended": False}, {"consent": False}, {"is_test": False}])
def test_ineligible_dialog_cannot_be_rated(expert_client, db_session, kwargs):
    dialog = add_dialog(db_session, **kwargs)
    assert expert_client.post(f"/expert/rate/{dialog.id}", data={"score": "3"}).status_code == 404


def test_stops_at_target(expert_client, db_session):
    dialogs = [add_dialog(db_session) for _ in range(RATING_TARGET + 1)]
    for dialog in dialogs[:RATING_TARGET]:
        expert_client.post(f"/expert/rate/{dialog.id}", data={"score": "3"})
    assert "dialog baholandi" in expert_client.get("/expert").text


def test_ahp_page_has_all_pairs(expert_client):
    page = expert_client.get("/expert/ahp").text
    assert page.count("<select") == 10
    assert "m3_0_1" in page


def test_ahp_saves_four_levels_and_gives_weights(expert_client, db_session):
    response = expert_client.post("/expert/ahp", data=form({"m0_0_1": "3", "m0_0_2": "3"}))
    assert "Baholar izchil" in response.text
    rows = db_session.scalars(select(AhpJudgment)).all()
    assert sorted(r.level for r in rows) == [0, 1, 2, 3]
    weights = load_weights(db_session)
    assert weights.dimensions["QD1"] > weights.dimensions["QD2"]
    assert weights.local["k7"] == pytest.approx(0.5)


def test_ahp_stores_reciprocals(expert_client, db_session):
    expert_client.post("/expert/ahp", data=form({"m3_0_1": "1/4"}))
    row = db_session.scalars(select(AhpJudgment).where(AhpJudgment.level == 3)).one()
    assert json.loads(row.matrix_json) == [[1.0, 0.25], [4.0, 1.0]]


def test_ahp_resubmit_replaces(expert_client, db_session):
    expert_client.post("/expert/ahp", data=form())
    expert_client.post("/expert/ahp", data=form())
    assert len(db_session.scalars(select(AhpJudgment)).all()) == 4


def test_ahp_page_prefills_saved_answer(expert_client):
    expert_client.post("/expert/ahp", data=form({"m3_0_1": "1/4"}))
    page = expert_client.get("/expert/ahp").text
    assert '<option value="1/4" selected>' in page


def test_ahp_warns_when_inconsistent(expert_client):
    values = {"m0_0_1": "9", "m0_0_2": "1/9", "m0_1_2": "9"}
    response = expert_client.post("/expert/ahp", data=form(values))
    assert "izchil emas" in response.text
    assert "CR =" in response.text


@pytest.mark.parametrize("bad", ["10", "abc", "1/10", ""])
def test_ahp_rejects_bad_values(expert_client, db_session, bad):
    response = expert_client.post("/expert/ahp", data=form({"m0_0_1": bad}))
    assert response.status_code == 400
    assert db_session.scalars(select(AhpJudgment)).all() == []


def test_two_experts_are_aggregated(expert_client, client, db_session):
    expert_client.post("/expert/ahp", data=form({"m3_0_1": "4"}))
    login_as(client, db_session, "exp2", "ekspert")
    client.post("/expert/ahp", data=form({"m3_0_1": "1"}))
    weights = load_weights(db_session)
    assert weights.experts == 2
    assert weights.local["k7"] == pytest.approx(2 / 3)
