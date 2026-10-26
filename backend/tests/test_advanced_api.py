import hashlib
import json
import os
import subprocess
import sys
from datetime import timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.advanced_risk import capacity
from app.brokers.demo import DemoBroker, demo_history
from app.core.config import ROOT, Settings
from app.database.models import Dataset, PortfolioSnapshot, RiskInputArtifact, RiskRun
from app.main import app


def analyze(client, **kwargs):
    return client.post("/api/v1/risk/analysis", json={"simulations": 2000, **kwargs})


def test_comparison_persistence_retrieval_and_replay(client, database):
    response = analyze(client)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["metadata"]["currency"] == "INR"
    assert result["metadata"]["sample_size"] == 252
    assert result["simulation"]["seed"] == 42
    assert (
        result["models"]["historical"]["expected_shortfall"]
        >= result["models"]["historical"]["var"]
    )
    assert sum(
        a["component_daily_volatility"] for a in result["attribution"]["assets"]
    ) == pytest.approx(result["daily_volatility"], abs=1e-14)
    assert result["annualized_volatility"] == pytest.approx(
        result["sample_annualized_volatility"], rel=1e-13
    )
    legacy = client.get("/api/risk").json()
    assert result["models"]["historical"]["var"] == pytest.approx(legacy["historical_var_amount"])
    assert client.get(f"/api/v1/risk/runs/{result['run_id']}").json()["result"] == result
    assert client.get("/api/v1/risk/runs").json()[0]["replayable"]
    repeated = analyze(client).json()
    assert repeated["metadata"]["input_hash"] == result["metadata"]["input_hash"]
    assert repeated["models"] == result["models"]
    replay = client.post(f"/api/v1/risk/runs/{result['run_id']}/replay")
    assert replay.status_code == 200, replay.text
    assert replay.json()["input_hash_matches"] and replay.json()["numerical_results_match"]
    assert replay.json()["result"]["models"] == result["models"]
    with Session(database) as db:
        assert len(db.scalars(select(PortfolioSnapshot)).all()) == 1
        assert len(db.scalars(select(RiskInputArtifact)).all()) == 1
        artifact = db.scalar(select(RiskInputArtifact))
        assert len(artifact.payload["estimation"]["prices"]) == 253
        assert "draws" not in json.dumps(artifact.payload)
        run = db.get(RiskRun, result["run_id"])
        assert run.schema_version == 2 and run.parameters["simulations"] == 2000
    comparison = client.post(
        "/api/v1/risk/runs/compare", json={"run_ids": [result["run_id"], repeated["run_id"]]}
    )
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["rows"][1]["var_delta"] == 0


@pytest.mark.parametrize("route", ["var", "expected-shortfall", "monte-carlo"])
def test_aliases_share_models(client, route):
    response = client.post(f"/api/v1/risk/{route}", json={"simulations": 2000, "confidence": 0.975})
    assert response.status_code == 201, response.text
    assert set(response.json()["models"]) == {"historical", "gaussian", "monte_carlo"}
    assert response.json()["metadata"]["confidence"] == 0.975


@pytest.mark.parametrize(
    "body",
    [
        {"confidence": 0.899},
        {"confidence": 0.996},
        {"simulations": 1},
        {"simulations": 100001},
        {"seed": -1},
        {"seed": True},
        {"window": 59},
        {"window": 252.5},
        {"shrinkage": 1.1},
        {"unexpected": True},
    ],
)
def test_validated_requests(client, body):
    response = analyze(client, **body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_strict_tail_minimum_and_auth(client):
    insufficient = analyze(client, confidence=0.995, window=126)
    assert insufficient.status_code == 422
    assert insufficient.json()["error"]["code"] == "INSUFFICIENT_HISTORY"
    assert analyze(client, mode="kite").status_code == 401
    assert analyze(client, dataset_id="not-demo").json()["error"]["code"] == "SOURCE_MODE_MISMATCH"
    assert (
        client.post(
            "/api/v1/risk/analysis", headers={"Origin": "https://evil.example"}, json={}
        ).status_code
        == 403
    )


def test_owner_authorization_for_all_saved_operations(client):
    first, second = analyze(client).json(), analyze(client, seed=1).json()
    with TestClient(app) as other:
        assert other.get("/api/v1/risk/runs").json() == []
        assert other.get(f"/api/v1/risk/runs/{first['run_id']}").status_code == 404
        assert other.post(f"/api/v1/risk/runs/{first['run_id']}/replay").status_code == 404
        assert (
            other.post(
                "/api/v1/risk/runs/compare", json={"run_ids": [first["run_id"], second["run_id"]]}
            ).status_code
            == 404
        )


def test_tampered_replay_artifact_is_rejected(client, database):
    result = analyze(client).json()
    with Session(database) as db:
        artifact = db.get(RiskInputArtifact, result["metadata"]["input_artifact_id"])
        payload = json.loads(json.dumps(artifact.payload))
        payload["estimation"]["prices"][0][0] *= 2
        artifact.payload = payload
        db.commit()
    response = client.post(f"/api/v1/risk/runs/{result['run_id']}/replay")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INPUT_INTEGRITY"


def test_tampered_model_parameters_are_rejected(client, database):
    result = analyze(client).json()
    with Session(database) as db:
        run = db.get(RiskRun, result["run_id"])
        run.parameters = {**run.parameters, "seed": 999}
        db.commit()
    response = client.post(f"/api/v1/risk/runs/{result['run_id']}/replay")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INPUT_INTEGRITY"


def test_bounded_engine_capacity(client):
    capacity.acquire()
    try:
        response = analyze(client)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "RISK_ENGINE_BUSY"
    finally:
        capacity.release()


def test_saved_comparison_covers_each_model(client):
    first = analyze(client, seed=1).json()
    second = analyze(client, seed=2, shrinkage=0.1).json()
    response = client.post(
        "/api/v1/risk/runs/compare", json={"run_ids": [first["run_id"], second["run_id"]]}
    )
    assert response.status_code == 200, response.text
    row = response.json()["rows"][1]
    assert row["gaussian_var_delta"] == pytest.approx(
        second["models"]["gaussian"]["var"] - first["models"]["gaussian"]["var"]
    )
    assert row["gaussian_es_delta"] == pytest.approx(
        second["models"]["gaussian"]["expected_shortfall"]
        - first["models"]["gaussian"]["expected_shortfall"]
    )
    assert row["monte_carlo_var_delta"] == pytest.approx(
        second["models"]["monte_carlo"]["var"] - first["models"]["monte_carlo"]["var"]
    )
    assert row["monte_carlo_es_delta"] == pytest.approx(
        second["models"]["monte_carlo"]["expected_shortfall"]
        - first["models"]["monte_carlo"]["expected_shortfall"]
    )


def test_catalog_and_synthetic_historical_replay(client):
    catalog = client.get("/api/v1/risk/scenarios").json()
    assert next(s for s in catalog if s["id"] == "synthetic_2026")["available"]
    assert not next(s for s in catalog if s["id"] == "pandemic_2020")["available"]
    response = client.post(
        "/api/v1/risk/stress-test",
        json={
            "kind": "historical",
            "name": "Synthetic replay test",
            "scenario_id": "synthetic_2026",
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["scenario_kind"] == "synthetic_replay"
    assert result["path"][-1]["value"] == pytest.approx(result["value_after"])
    assert sum(a["pnl"] for a in result["assets"]) == pytest.approx(result["pnl"])
    assert sum(s["pnl"] for s in result["sectors"]) == pytest.approx(result["pnl"])
    assert result["reference_risk"] is not None
    replay = client.post(f"/api/v1/risk/runs/{result['run_id']}/replay")
    assert replay.status_code == 200, replay.text
    assert replay.json()["numerical_results_match"] and replay.json()["input_hash_matches"]
    denied = client.post(
        "/api/v1/risk/stress-test", json={"kind": "historical", "scenario_id": "pandemic_2020"}
    )
    assert denied.status_code == 422


def test_hypothetical_and_scenario_comparison(client):
    a = client.post(
        "/api/v1/risk/stress-test",
        json={"kind": "hypothetical", "market_shock": -0.1, "sector_shocks": {"Technology": -0.2}},
    )
    assert a.status_code == 201, a.text
    result = a.json()
    for asset in result["assets"]:
        assert asset["shock_return"] == (-0.2 if asset["sector"] == "Technology" else -0.1)
    b = client.post(
        "/api/v1/risk/stress-test", json={"kind": "hypothetical", "market_shock": -0.2}
    ).json()
    compared = client.post(
        "/api/v1/risk/runs/compare", json={"run_ids": [result["run_id"], b["run_id"]]}
    )
    assert compared.status_code == 200
    assert compared.json()["rows"][1]["pnl_delta"] == pytest.approx(b["pnl"] - result["pnl"])


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "hypothetical"},
        {"kind": "hypothetical", "market_shock": -1.1},
        {"kind": "historical", "start": "2026-01-05", "end": "2026-01-01"},
        {"kind": "historical", "scenario_id": "synthetic_2026", "market_shock": -0.1},
        {"kind": "hypothetical", "market_shock": -0.1, "start": "2026-01-01"},
    ],
)
def test_stress_request_validation(client, body):
    assert client.post("/api/v1/risk/stress-test", json=body).status_code == 422


def test_real_mode_with_no_estimation_history_and_separate_old_replay(client, monkeypatch):
    portfolio = DemoBroker().portfolio().model_copy(update={"mode": "kite", "synthetic": False})
    monkeypatch.setattr("app.api.advanced_risk.snapshot", lambda mode, session: portfolio)
    assert analyze(client, mode="kite").json()["error"]["code"] == "HISTORY_REQUIRED"
    direct = client.post(
        "/api/v1/risk/stress-test",
        json={"mode": "kite", "kind": "hypothetical", "market_shock": -0.1},
    )
    assert direct.status_code == 201, direct.text
    assert direct.json()["reference_risk"] is None
    assert "unavailable" in " ".join(direct.json()["metadata"]["warnings"])
    frame, _ = demo_history()
    # Synthetic contract-test prices explicitly labeled here; no real-provider result is claimed.
    frame.date = frame.date - timedelta(days=1800)
    response = client.post(
        "/api/history/import",
        files={"file": ("test.csv", frame.to_csv(index=False).encode())},
        data={
            "source": "Synthetic historical replay contract-test input",
            "adjustment": "split_dividend_adjusted",
        },
    )
    dataset_id = response.json()["id"]
    dates = sorted(frame.date.unique())
    start, end = (
        pd.Timestamp(dates[-30]).date().isoformat(),
        pd.Timestamp(dates[-1]).date().isoformat(),
    )
    replay = client.post(
        "/api/v1/risk/stress-test",
        json={
            "mode": "kite",
            "kind": "historical",
            "scenario_dataset_id": dataset_id,
            "start": start,
            "end": end,
        },
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["reference_risk"] is None
    assert replay.json()["observations"] == 30
    assert (
        client.get(f"/api/v1/risk/scenarios?mode=kite&dataset_id={dataset_id}").status_code == 200
    )


def test_adapter_import_and_hash_integrity(client, database, monkeypatch):
    frame, _ = demo_history()
    monkeypatch.setattr(
        "app.integrations.providers.providers.adjusted_history", lambda mapping, currency: frame
    )
    imported = client.post(
        "/api/history/alpha-vantage",
        json={
            "mapping": {"NSE:TEST": "TEST"},
            "currency": "INR",
            "currency_and_venue_verified": True,
        },
    )
    assert imported.status_code == 201
    dataset_id = imported.json()["id"]
    portfolio = DemoBroker().portfolio().model_copy(update={"mode": "kite", "synthetic": False})
    monkeypatch.setattr("app.api.advanced_risk.snapshot", lambda mode, session: portfolio)
    result = analyze(client, mode="kite", dataset_id=dataset_id)
    assert result.status_code == 201, result.text
    with Session(database) as db:
        dataset = db.get(Dataset, dataset_id)
        assert (
            hashlib.sha256(dataset.records.encode()).hexdigest()
            == dataset.provenance["content_hash"]
        )
        dataset.records = dataset.records.replace('"close":', '"close":1,"ignored":', 1)
        db.commit()
    assert (
        analyze(client, mode="kite", dataset_id=dataset_id).json()["error"]["code"]
        == "SOURCE_INTEGRITY"
    )


def test_sqlite_migration_preserves_legacy_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    environment = {**os.environ, "DATABASE_URL": url}
    command = [sys.executable, "-m", "alembic", "-c", str(ROOT / "backend/alembic.ini")]
    subprocess.run(command + ["upgrade", "0001"], env=environment, check=True, capture_output=True)
    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO risk_runs (id,owner,input_hash,methodology,result,created_at) VALUES ('legacy','test','hash','v1','{}','2026-01-01')"
            )
        )
    subprocess.run(command + ["upgrade", "head"], env=environment, check=True, capture_output=True)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT schema_version,kind FROM risk_runs WHERE id='legacy'")
        ).one()
        assert row == (1, "legacy")
    subprocess.run(
        command + ["downgrade", "0001"], env=environment, check=True, capture_output=True
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM risk_runs")).scalar_one() == 1
    engine.dispose()


def test_relative_sqlite_configuration_is_independent_of_process_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    configured = Settings(database_url="sqlite:///./vantage.db")
    from sqlalchemy.engine import make_url

    assert make_url(configured.database_url).database == str(ROOT / "vantage.db")
    assert Settings(database_url="sqlite:///:memory:").database_url == "sqlite:///:memory:"
