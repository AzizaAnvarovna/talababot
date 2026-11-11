import pytest
from sqlalchemy import select

from app.db.models import SlangTerm
from app.nlp import classifier
from app.nlp.train_svm import train
from app.settings_store import load_settings

VALID = {"tau": "0,7", "sigma": "0.4", "active_model": "rule-based"}


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/admin/settings"), ("post", "/admin/settings"), ("get", "/admin/slang")],
)
def test_requires_login(client, method, path):
    assert getattr(client, method)(path, follow_redirects=False).status_code == 303


def test_settings_page_shows_defaults(admin_client):
    response = admin_client.get("/admin/settings")
    assert response.status_code == 200
    assert 'value="0.6"' in response.text


def test_save_settings_accepts_decimal_comma(admin_client, db_session):
    response = admin_client.post("/admin/settings", data=VALID)
    assert "Sozlamalar saqlandi" in response.text
    db_session.expire_all()
    saved = load_settings(db_session)
    assert saved.tau == 0.7
    assert saved.sigma == 0.4


@pytest.mark.parametrize("tau", ["2", "-0.1", "abc", ""])
def test_invalid_threshold_is_rejected(admin_client, db_session, tau):
    assert admin_client.post("/admin/settings", data=VALID | {"tau": tau}).status_code == 400
    assert load_settings(db_session).tau == 0.6


def test_untrained_model_cannot_be_activated(admin_client, monkeypatch, tmp_path):
    monkeypatch.setattr(classifier, "MODEL_PATH", tmp_path / "none.joblib")
    response = admin_client.post("/admin/settings", data=VALID | {"active_model": "svm"})
    assert response.status_code == 400


def test_ab_needs_two_different_ready_models(admin_client, db_session, monkeypatch, tmp_path):
    path = tmp_path / "svm.joblib"
    monkeypatch.setattr(classifier, "MODEL_PATH", path)
    ab = VALID | {"ab_enabled": "on", "ab_model_a": "rule-based", "ab_model_b": "rule-based"}
    assert admin_client.post("/admin/settings", data=ab).status_code == 400

    train(["a b c", "a b d", "a b e", "x y z", "x y w", "x y v"], ["S"] * 3 + ["Y"] * 3, path)
    admin_client.post("/admin/settings", data=ab | {"ab_model_b": "svm"})
    db_session.expire_all()
    assert load_settings(db_session).ab_enabled is True


def test_slang_add_normalizes_update_delete(admin_client, db_session):
    admin_client.post("/admin/slang", data={"term": " STIPUXA ", "replacement": "Stipendiya"})
    admin_client.post("/admin/slang", data={"term": "stipuxa", "replacement": "grant"})
    db_session.expire_all()
    term = db_session.scalars(select(SlangTerm)).one()
    assert (term.term, term.replacement) == ("stipuxa", "grant")
    assert "stipuxa" in admin_client.get("/admin/slang").text

    admin_client.post(f"/admin/slang/{term.id}/delete")
    db_session.expire_all()
    assert db_session.scalars(select(SlangTerm)).all() == []


def test_empty_slang_is_not_saved(admin_client, db_session):
    response = admin_client.post("/admin/slang", data={"term": "", "replacement": "x"})
    assert "toʻldirilishi shart" in response.text
    assert db_session.scalars(select(SlangTerm)).all() == []


def test_delete_missing_slang_returns_404(admin_client):
    assert admin_client.post("/admin/slang/999/delete").status_code == 404
