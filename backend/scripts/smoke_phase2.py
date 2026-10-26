"""Database-backed integration smoke; use DATABASE_URL to select PostgreSQL/SQLite."""

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database.session import engine
from app.main import app


def main():
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/portfolio").json()["synthetic"] is True
        assert client.get("/api/risk").status_code == 200
        response = client.post(
            "/api/v1/risk/analysis",
            json={"confidence": 0.975, "simulations": 2000, "seed": 2026, "shrinkage": 0.1},
        )
        assert response.status_code == 201, response.text
        run = response.json()
        replay = client.post(f"/api/v1/risk/runs/{run['run_id']}/replay")
        assert replay.status_code == 200, replay.text
        assert replay.json()["input_hash_matches"] and replay.json()["numerical_results_match"]
        assert client.get("/api/v1/risk/runs?mode=demo").json()
        stress = client.post(
            "/api/v1/risk/stress-test", json={"kind": "historical", "scenario_id": "synthetic_2026"}
        )
        assert stress.status_code == 201, stress.text
        stress_replay = client.post(f"/api/v1/risk/runs/{stress.json()['run_id']}/replay")
        assert stress_replay.status_code == 200, stress_replay.text
        assert stress_replay.json()["numerical_results_match"]
        compare = client.post(
            "/api/v1/risk/runs/compare",
            json={"run_ids": [run["run_id"], replay.json()["replayed_run_id"]]},
        )
        assert compare.status_code == 200, compare.text
        assert compare.json()["rows"][1]["var_delta"] == 0
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM portfolio_snapshots")).scalar_one() >= 1
        )
        assert (
            connection.execute(text("SELECT count(*) FROM risk_input_artifacts")).scalar_one() >= 1
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM risk_runs WHERE schema_version=2")
            ).scalar_one()
            >= 4
        )
    print(
        "Database-backed Phase 1/2 readiness, analysis, ownership, comparison, immutable inputs and exact analysis/stress replay: PASS"
    )


if __name__ == "__main__":
    main()
