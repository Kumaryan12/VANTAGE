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
    assert detail["dataset"]["covariance_hash"] == point["dataset"]["covariance_hash"]
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


def study(client, path, body):
    response = client.post(path, json=body)
    assert response.status_code == 202, response.text
    queue.futures[response.json()["id"]].result(timeout=40)
    detail = client.get(f"/api/v1/optimization/runs/{response.json()['id']}").json()
    assert detail["status"] in ("completed", "partial"), detail
    return detail


def test_risk_turnover_curve_and_six_sensitivity_axes(agent_client):
    client, _ = agent_client
    frontier = study(
        client,
        "/api/v1/optimization/frontier",
        {"base": {}, "turnover_budgets": [0, 0.05, 0.1, 0.15, 0.25]},
    )
    points = frontier["result"]["points"]
    assert len(points) == 5
    assert points[0]["solution"]["status"] == "infeasible"
    feasible = [p["solution"]["annual_volatility"] for p in points if p["solution"]["feasible"]]
    assert len(feasible) >= 2
    assert all(b <= a + 1e-7 for a, b in zip(feasible, feasible[1:], strict=False))
    assert frontier["result"]["plot"][0]["annual_volatility"] is None
    replay = client.post(f"/api/v1/optimization/runs/{frontier['id']}/reproduce")
    assert replay.status_code == 202, replay.text
    queue.futures[replay.json()["id"]].result(timeout=30)
    assert (
        client.get(f"/api/v1/optimization/runs/{replay.json()['id']}").json()["result"][
            "reproduction_match"
        ]
        is True
    )
    sensitivity = study(
        client,
        "/api/v1/optimization/sensitivity",
        {
            "base": {},
            "variations": [
                {"kind": "window", "value": 126},
                {"kind": "shrinkage", "value": 0.1},
                {"kind": "max_weight", "value": 0.25},
                {"kind": "sector_max", "sector": "Technology", "value": 0.15},
                {"kind": "turnover", "value": 0.1},
                {"kind": "cost_penalty", "value": 5},
            ],
        },
    )
    assert len(sensitivity["result"]["points"]) == 7
    assert sensitivity["result"]["points"][1]["dataset"]["observations"] == 126
    assert (
        sensitivity["result"]["points"][2]["dataset"]["covariance_hash"]
        != sensitivity["result"]["points"][0]["dataset"]["covariance_hash"]
    )
    assert sensitivity["result"]["points"][-1]["parameters"]["objective"] == "risk_cost"
    assert sensitivity["result"]["points"][0]["parameters"]["objective"] == "min_variance"


def test_efficient_frontier_is_gated_on_explicit_complete_returns(agent_client):
    client, _ = agent_client
    assert (
        client.post(
            "/api/v1/optimization/frontier",
            json={"mode": "efficient", "return_targets": [0.05, 0.1]},
        ).status_code
        == 422
    )
    from app.brokers.demo import DemoBroker

    instruments = [h.instrument for h in DemoBroker().portfolio().holdings]
    assumed = {
        "annual_returns": {name: 0.05 + 0.01 * i for i, name in enumerate(instruments)},
        "source": "Explicit hypothetical annual assumptions for a synthetic frontier validation, not forecasts.",
    }
    detail = study(
        client,
        "/api/v1/optimization/frontier",
        {
            "base": {"expected_returns": assumed},
            "mode": "efficient",
            "return_targets": [0.06, 0.15],
        },
    )
    assert detail["result"]["points"][0]["solution"]["feasible"]
    assert detail["result"]["points"][0]["solution"]["expected_annual_return"] >= 0.06 - 1e-7
    assert detail["result"]["points"][1]["solution"]["status"] == "infeasible"


def test_identical_counterfactual_shocks_and_saved_comparison(agent_client):
    client, _ = agent_client
    first = completed(client)
    response = client.post(
        "/api/v1/optimization/counterfactual",
        json={
            "run_id": first["id"],
            "scenario": {"kind": "hypothetical", "sector_shocks": {"Technology": -0.15}},
        },
    )
    assert response.status_code == 200, response.text
    stress = response.json()
    assert stress["current"]["pnl"] == pytest.approx(-85718.2399437387)
    point = first["result"]["points"][0]
    weight = sum(a["proposed_weight"] for a in point["allocations"] if a["sector"] == "Technology")
    assert stress["proposed"]["pnl"] == pytest.approx(
        -0.15 * first["dataset"]["sleeve_notional"] * weight
    )
    assert stress["proposed"]["pnl_reconciliation_residual"] == pytest.approx(0, abs=1e-8)
    historical = client.post(
        "/api/v1/optimization/counterfactual",
        json={
            "run_id": first["id"],
            "scenario": {"kind": "historical", "scenario_id": "synthetic_2026"},
        },
    )
    assert historical.status_code == 200, historical.text
    assert historical.json()["source"]["synthetic"] is True
    assert (
        client.post(
            "/api/v1/optimization/counterfactual",
            json={
                "run_id": first["id"],
                "scenario": {"kind": "historical", "scenario_id": "pandemic_2020"},
            },
        ).status_code
        == 422
    )
    second = completed(client, constraints={"max_weight": 0.22, "max_turnover": 0.15})
    comparison = client.post(
        "/api/v1/optimization/compare", json={"run_ids": [first["id"], second["id"]]}
    )
    assert comparison.status_code == 200, comparison.text
    assert len(comparison.json()["runs"]) == 2
    third = completed(client, shrinkage=0.1)
    assert (
        client.post(
            "/api/v1/optimization/compare", json={"run_ids": [first["id"], third["id"]]}
        ).status_code
        == 409
    )
    with TestClient(client.app) as other:
        assert (
            other.post(
                "/api/v1/optimization/counterfactual",
                json={
                    "run_id": first["id"],
                    "scenario": {"kind": "hypothetical", "market_shock": -0.1},
                },
            ).status_code
            == 404
        )


def test_counterfactual_reproduction_and_result_integrity(agent_client):
    from app.database.models import OptimizationCounterfactual

    client, engine = agent_client
    saved = completed(client)
    original = client.post(
        "/api/v1/optimization/counterfactual",
        json={
            "run_id": saved["id"],
            "scenario": {"kind": "historical", "scenario_id": "synthetic_2026"},
        },
    ).json()
    replay = client.post(f"/api/v1/optimization/counterfactuals/{original['id']}/reproduce")
    assert replay.status_code == 200, replay.text
    assert replay.json()["current"] == original["current"]
    assert replay.json()["proposed"] == original["proposed"]
    assert replay.json()["input_hash"] == original["input_hash"]
    with TestClient(client.app) as other:
        assert (
            other.post(
                f"/api/v1/optimization/counterfactuals/{original['id']}/reproduce"
            ).status_code
            == 404
        )
    with Session(engine) as db:
        row = db.get(OptimizationCounterfactual, original["id"])
        row.payload = {**row.payload, "proposed": {**row.payload["proposed"], "pnl": 1}}
        db.commit()
    assert client.get(f"/api/v1/optimization/runs/{saved['id']}/counterfactuals").status_code == 409
    assert (
        client.post(f"/api/v1/optimization/counterfactuals/{original['id']}/reproduce").status_code
        == 409
    )


def test_worker_solver_failure_has_no_partial_allocation_and_releases_capacity(
    agent_client, monkeypatch
):
    import app.optimization.service as service

    client, _ = agent_client
    original = service.calculate_point

    def failed(*args, **kwargs):
        raise RuntimeError("Upstream private response must never leak")

    monkeypatch.setattr(service, "calculate_point", failed)
    response = client.post("/api/v1/optimization/run", json={})
    assert response.status_code == 202
    queue.futures[response.json()["id"]].result(timeout=30)
    detail = client.get(f"/api/v1/optimization/runs/{response.json()['id']}").json()
    assert detail["status"] == "failed" and detail["result"] is None
    assert "private" not in str(detail["error"])
    monkeypatch.setattr(service, "calculate_point", original)
    assert completed(client)["status"] == "completed"
