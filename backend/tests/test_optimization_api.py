import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database.models import OptimizationRun, RiskInputArtifact
from app.optimization.service import queue


def completed(client, **settings):
    response = client.post("/api/v1/optimization/run", json=settings)
    assert response.status_code == 202, response.text
    ident = response.json()["id"]
    queue.futures[ident].result(timeout=30)
    result = client.get(f"/api/v1/optimization/runs/{ident}")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "completed", result.text
    return result.json()


def test_saved_minimum_variance_slice_risk_and_reproduction(agent_client):
    client, engine = agent_client
    detail = completed(client)
    point = detail["result"]["points"][0]
    assert point["solution"]["feasible"], point
    assert sum(point["solution"]["weights"]) == pytest.approx(1, abs=1e-12)
    assert max(point["solution"]["weights"]) <= 0.2 + 1e-7
    assert point["solution"]["turnover"] <= 0.15 + 1e-7
    assert point["solution"]["annual_variance"] == pytest.approx(
        point["comparison"]["proposed"]["annual_variance"], abs=1e-12
    )
    assert point["comparison"]["current"]["notional"] == point["comparison"]["proposed"]["notional"]
    legacy = client.post(
        "/api/v1/risk/analysis",
        json={"simulations": 2000, "seed": 42, "window": 252, "confidence": 0.95},
    ).json()
    assert point["comparison"]["current"]["historical_var"] == legacy["models"]["historical"]["var"]
    assert point["comparison"]["current"]["gaussian_es"] == pytest.approx(
        legacy["models"]["gaussian"]["expected_shortfall"]
    )
    assert "not assumed zero" in detail["dataset"]["account_cash"]
    replay = client.post(f"/api/v1/optimization/runs/{detail['id']}/reproduce")
    assert replay.status_code == 202, replay.text
    queue.futures[replay.json()["id"]].result(timeout=30)
    reproduced = client.get(f"/api/v1/optimization/runs/{replay.json()['id']}").json()
    assert reproduced["result"]["reproduction_match"] is True, reproduced
    assert client.get("/api/v1/optimization/runs").json()
    with TestClient(client.app) as other:
        assert other.get(f"/api/v1/optimization/runs/{detail['id']}").status_code == 404
        assert other.post(f"/api/v1/optimization/runs/{detail['id']}/reproduce").status_code == 404
    with Session(engine) as db:
        row = db.get(OptimizationRun, detail["id"])
        artifact = db.get(RiskInputArtifact, row.artifact_id)
        artifact.payload = {**artifact.payload, "tampered": True}
        db.commit()
    assert client.post(f"/api/v1/optimization/runs/{detail['id']}/reproduce").status_code == 409


def test_infeasible_request_stays_saved_without_proposed_weights(agent_client):
    client, _ = agent_client
    detail = completed(client, constraints={"max_weight": 0.2, "max_turnover": 0})
    point = detail["result"]["points"][0]
    assert point["solution"]["status"] == "infeasible"
    assert point["solution"]["weights"] is None and point["comparison"] is None
    assert point["current_metrics"]["annual_volatility"] > 0
    assert not point["allocations"]
    assert any("turnover" in message for message in point["solution"]["diagnostics"])


def test_optimization_source_authorization_validation_and_capacity(agent_client):
    client, _ = agent_client
    assert client.post("/api/v1/optimization/run", json={"mode": "kite"}).status_code == 401
    assert client.post("/api/v1/optimization/run", json={"window": 1260}).status_code == 422
    assert client.post("/api/v1/optimization/run", json={"owner": "foreign"}).status_code == 422
    assert (
        client.post(
            "/api/v1/optimization/run", json={"constraints": {"asset_max": {"NEW": 0.3}}}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/optimization/run", json={}, headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    queue.capacity.acquire()
    try:
        assert client.post("/api/v1/optimization/run", json={}).status_code == 503
    finally:
        queue.capacity.release()
