import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.database.models import Base, ResearchExperiment, RiskInputArtifact
from app.database.session import get_db
from app.main import app
from app.ml.service import queue


@pytest.fixture
def research_client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'research.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings(), "model_artifact_dir", str(tmp_path / "models"))

    def db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = db
    with TestClient(app) as client:
        yield client, engine
    for future in list(queue.futures.values()):
        future.result(timeout=30)
    app.dependency_overrides.clear()
    engine.dispose()


def completed(client, **parameters):
    response = client.post(
        "/api/v1/ml/backtest", json={"max_trees": 40, "search_candidates": 2, **parameters}
    )
    assert response.status_code == 202, response.text
    ident = response.json()["id"]
    queue.futures[ident].result(timeout=30)
    detail = client.get(f"/api/v1/ml/experiments/{ident}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "completed", detail.text
    return detail.json()


def test_research_job_registry_artifacts_explanations_and_reproduction(research_client):
    client, engine = research_client
    detail = completed(client)
    ident = detail["id"]
    assert detail["comparison"]["matched_observations"] == 100
    models = client.get(f"/api/v1/ml/models?experiment_id={ident}")
    assert models.status_code == 200, models.text
    assert len(models.json()) == 4
    model = next(m for m in models.json() if m["kind"] == "lightgbm")
    assert model["role"] == "candidate"
    forecasts = client.get(f"/api/v1/ml/models/{model['id']}/forecasts").json()
    assert len(forecasts) == 100 and all(p["origin"] < p["target_end"] for p in forecasts)
    series = client.get(f"/api/v1/ml/experiments/{ident}/series")
    assert series.status_code == 200, series.text
    assert len(series.json()) == 100
    explanation = client.get(f"/api/v1/ml/models/{model['id']}/explain")
    assert explanation.status_code == 200, explanation.text
    assert abs(explanation.json()["reconstruction_residual"]) < 1e-14
    assert explanation.json()["forecast_variance"] == forecasts[-1]["forecast_variance"]
    artifact = client.get(f"/api/v1/ml/models/{model['id']}/artifact")
    assert artifact.status_code == 200 and artifact.content.startswith(b"PK")
    report = client.get(f"/api/v1/ml/experiments/{ident}/report")
    assert report.status_code == 200 and "SYNTHETIC" in report.json()["markdown"]
    repro = client.post(f"/api/v1/ml/experiments/{ident}/reproduce")
    assert repro.status_code == 202, repro.text
    queue.futures[repro.json()["id"]].result(timeout=30)
    second = client.get(f"/api/v1/ml/experiments/{repro.json()['id']}").json()
    assert second["reproduction_match"] is True
    comparison = client.post(
        "/api/v1/ml/experiments/compare", json={"experiment_ids": [ident, second["id"]]}
    )
    assert comparison.status_code == 200, comparison.text
    review = client.post(
        f"/api/v1/ml/models/{model['id']}/governance",
        json={
            "role": "champion",
            "rationale": "Reviewed matched QLIKE, coverage and synthetic-data limitations; development candidate only.",
            "acknowledge_limitations": True,
        },
    )
    assert review.status_code == 200, review.text
    assert review.json()["role"] == "champion" and review.json()["governance"]
    with TestClient(app) as other:
        assert other.get(f"/api/v1/ml/experiments/{ident}").status_code == 404
        assert other.get(f"/api/v1/ml/models/{model['id']}/artifact").status_code == 404
        assert other.post(f"/api/v1/ml/experiments/{ident}/reproduce").status_code == 404
    with Session(engine) as db:
        assert db.scalar(select(ResearchExperiment)).input_hash


def test_failed_jobs_and_bounded_queue_are_explicit(research_client, monkeypatch):
    client, _ = research_client
    queue.capacity.acquire()
    try:
        assert client.post("/api/v1/ml/train", json={}).status_code == 503
    finally:
        queue.capacity.release()

    def fail(*args, **kwargs):
        raise AppError(
            "TEST_TRAINING_FAILURE", "Deliberate test fitting failure; no forecasts generated."
        )

    monkeypatch.setattr("app.ml.service.execute_research", fail)
    response = client.post("/api/v1/ml/train", json={})
    assert response.status_code == 202
    ident = response.json()["id"]
    queue.futures[ident].result(timeout=30)
    status = client.get(f"/api/v1/ml/jobs/{ident}").json()
    assert status["status"] == "failed" and status["error"]["code"] == "TEST_TRAINING_FAILURE"
    assert client.get(f"/api/v1/ml/models?experiment_id={ident}").json() == []


def test_research_validation_window_and_integrity(research_client):
    client, engine = research_client
    assert client.post("/api/v1/ml/train", json={"mode": "kite"}).status_code == 401
    assert client.post("/api/v1/ml/train", json={"test_size": 500}).status_code == 422
    assert client.post("/api/v1/ml/train", json={"max_trees": 5000}).status_code == 422
    assert (
        client.post(
            "/api/v1/ml/train", json={}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    detail = completed(client, test_size=40, validation_size=30)
    ident = detail["id"]
    bad = client.get(f"/api/v1/ml/comparison?experiment_id={ident}&start=1900-01-01")
    assert bad.status_code == 422
    model = client.get(f"/api/v1/ml/models?experiment_id={ident}").json()[0]
    assert (
        client.post(
            f"/api/v1/ml/models/{model['id']}/governance",
            json={
                "role": "champion",
                "rationale": "Documented review of an insufficiently short sample.",
                "acknowledge_limitations": True,
            },
        ).status_code
        == 422
    )
    with Session(engine) as db:
        exp = db.get(ResearchExperiment, ident)
        artifact = db.get(RiskInputArtifact, exp.input_artifact_id)
        payload = json.loads(json.dumps(artifact.payload))
        payload["portfolio_history"]["prices"][0][0] *= 2
        artifact.payload = payload
        db.commit()
    assert client.post(f"/api/v1/ml/experiments/{ident}/reproduce").status_code == 409


def test_interrupted_worker_and_artifact_tamper(research_client):
    client, engine = research_client
    detail = completed(client, test_size=40, validation_size=30)
    ident = detail["id"]
    with Session(engine) as db:
        exp = db.get(ResearchExperiment, ident)
        exp.status = "running"
        exp.runner_id = "previous-process"
        db.commit()
    response = client.get(f"/api/v1/ml/jobs/{ident}").json()
    assert response["status"] == "interrupted" and response["error"]["code"] == "WORKER_INTERRUPTED"
    models = client.get(f"/api/v1/ml/models?experiment_id={ident}").json()
    model = next(m for m in models if m["kind"] == "lightgbm")
    from pathlib import Path

    path = Path(settings().model_artifact_dir) / model["artifact_files"][0]["path"]
    path.write_text("tampered")
    assert client.get(f"/api/v1/ml/models/{model['id']}/artifact").status_code == 409
