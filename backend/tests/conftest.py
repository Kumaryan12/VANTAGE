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


@pytest.fixture
def agent_client(tmp_path, monkeypatch):
    from app.agent.service import queue
    from app.core.config import settings
    from app.documents.service import queue as document_queue

    engine = create_engine(
        f"sqlite:///{tmp_path / 'agent.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings(), "model_artifact_dir", str(tmp_path / "models"))
    monkeypatch.setattr(settings(), "document_storage_dir", str(tmp_path / "documents"))
    monkeypatch.setattr(settings(), "openai_api_key", "")

    def db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = db
    with TestClient(app) as client:
        yield client, engine
    for future in list(document_queue.futures.values()):
        future.result(timeout=30)
    for future in list(queue.futures.values()):
        future.result(timeout=30)
    queue.tool_executor.submit(lambda: None).result(timeout=30)
    app.dependency_overrides.clear()
    engine.dispose()
