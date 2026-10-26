"""Opt-in paid provider contract smoke using only fresh synthetic research evidence."""

import os

from fastapi.testclient import TestClient

from app.agent.service import queue
from app.core.config import settings
from app.main import app
from app.ml.service import queue as research_queue


def main():
    if os.environ.get("VANTAGE_LIVE_AI") != "1" or not settings().openai_api_key:
        raise SystemExit(
            "Opt-in only: configure OPENAI_API_KEY and set VANTAGE_LIVE_AI=1. No provider request made."
        )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ml/backtest", json={"max_trees": 40, "search_candidates": 2}
        )
        assert response.status_code == 202, response.text
        experiment = response.json()["id"]
        research_queue.futures[experiment].result(timeout=60)
        response = client.post(
            "/api/v1/agent/investigate",
            json={
                "question": "Compare forecasting models on QLIKE, sample size, and limitations. Use the selected experiment and publish only verified facts.",
                "experiment_id": experiment,
                "engine": "llm",
                "external_data_consent": True,
                "timeout_seconds": 90,
            },
        )
        assert response.status_code == 202, response.text
        ident = response.json()["id"]
        queue.futures[ident].result(timeout=100)
        detail = client.get(f"/api/v1/agent/investigations/{ident}").json()
        assert detail["status"] == "completed", detail.get("error")
        assert detail["answer"]["numerical_verification"] == "passed"
        assert detail["usage"]["provider_requests"] >= 2
        print("Opt-in actual provider tool calling and verified synthetic comparison: PASS")
        print("Provider/model", detail["provider"], "usage", detail["usage"])


if __name__ == "__main__":
    main()
