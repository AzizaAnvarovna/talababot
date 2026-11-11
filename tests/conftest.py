import os

os.environ.update(
    SECRET_KEY="test-secret",
    USER_HASH_SALT="test-salt",
    BOT_API_TOKEN="test-bot-token",
    DELIVERY_KEY="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    DATABASE_URL="sqlite://",
    TEST_MODE="true",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import create_or_update_staff  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db_session():
    from sqlalchemy import create_engine

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


PASSWORD = "test-password"


def login_as(client, db, login, role):
    create_or_update_staff(db, login, PASSWORD, role)
    response = client.post(
        "/admin/login", data={"login": login, "password": PASSWORD}, follow_redirects=False
    )
    assert response.status_code == 303
    return client


@pytest.fixture
def admin_client(client, db_session):
    return login_as(client, db_session, "admin", "admin")


@pytest.fixture
def operator_client(client, db_session):
    return login_as(client, db_session, "op1", "operator")
