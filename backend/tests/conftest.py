import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.sessions import store
from app.database.models import Base
from app.database.session import get_db
from app.main import app


@pytest.fixture
def database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(database):
    def override_db():
        with Session(database) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    store.items.clear()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    store.items.clear()
