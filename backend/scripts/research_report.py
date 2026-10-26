"""Execute real synthetic research, verify saved-input reproduction, and render evidence."""

import argparse
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database.session import engine
from app.main import app
from app.ml.service import queue

ROOT = Path(__file__).resolve().parents[2]


def run(client, body):
    response = client.post("/api/v1/ml/backtest", json=body)
    assert response.status_code == 202, response.text
    ident = response.json()["id"]
    queue.futures[ident].result(timeout=180)
    detail = client.get(f"/api/v1/ml/experiments/{ident}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "completed", detail.text
    return detail.json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Short DB-backed integration verification; no tracked report",
    )
    args = parser.parse_args()
    with TestClient(app) as client:
        detail = run(client, {"max_trees": 40, "search_candidates": 2} if args.smoke else {})
        ident = detail["id"]
        assert detail["synthetic"] is True
        assert detail["comparison"]["matched_observations"] == 100
        models = client.get(f"/api/v1/ml/models?experiment_id={ident}").json()
        assert len(models) == 4
        lightgbm = next(m for m in models if m["kind"] == "lightgbm")
        explanation = client.get(f"/api/v1/ml/models/{lightgbm['id']}/explain")
        assert explanation.status_code == 200, explanation.text
        assert abs(explanation.json()["reconstruction_residual"]) < 1e-14
        assert client.get(f"/api/v1/ml/models/{lightgbm['id']}/artifact").content.startswith(b"PK")
        reproduction = client.post(f"/api/v1/ml/experiments/{ident}/reproduce")
        assert reproduction.status_code == 202, reproduction.text
        second_id = reproduction.json()["id"]
        queue.futures[second_id].result(timeout=180)
        second = client.get(f"/api/v1/ml/experiments/{second_id}").json()
        assert second["reproduction_match"] is True, second
        assert (
            client.post(
                "/api/v1/ml/experiments/compare", json={"experiment_ids": [ident, second_id]}
            ).status_code
            == 200
        )
        with TestClient(app) as stranger:
            assert stranger.get(f"/api/v1/ml/experiments/{ident}").status_code == 404
        if not args.smoke:
            markdown = client.get(f"/api/v1/ml/experiments/{ident}/report").json()["markdown"]
            output = ROOT / "docs/research/volatility_model_comparison.md"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(markdown)
            print(
                f"Executed default experiment and reproduction; report: {output.relative_to(ROOT)}"
            )
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM research_forecasts")).scalar_one()
                >= 800
            )
        print(
            f"Research persistence, four actual models, 100 matched targets, artifact reload/TreeSHAP, ownership and saved-input reproduction: PASS ({engine.dialect.name})"
        )
        for model in detail["comparison"]["models"]:
            metrics = model["metrics"]
            print(
                model["kind"],
                "QLIKE",
                metrics["qlike"],
                "VaR95",
                metrics["coverage95"]["exceptions"],
                "VaR99",
                metrics["coverage99"]["exceptions"],
            )


if __name__ == "__main__":
    main()
