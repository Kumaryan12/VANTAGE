import json
from collections import Counter

from fastapi.testclient import TestClient

from app.agent.evaluation import GOLDEN_PATH, queue
from app.agent.service import classify


def test_golden_dataset_has_fixed_thresholds_and_diverse_reference_cases():
    golden = json.loads(GOLDEN_PATH.read_text())
    assert len(golden["cases"]) >= 60
    assert len({c["id"] for c in golden["cases"]}) == len(golden["cases"])
    assert len(Counter(c["category"] for c in golden["cases"])) >= 10
    assert golden["thresholds"]["safety"] == 1
    assert all(c["expected_behavior"] and c["permitted_evidence"] for c in golden["cases"])
    assert classify("Calculate portfolio VaR and Expected Shortfall.") == "risk"
    assert classify("Compare changes over time across risk snapshots.") == "changes"


def test_full_golden_run_records_real_scores_failures_and_owner_scope(agent_client):
    client, _ = agent_client
    response = client.post("/api/v1/agent/evaluation-runs")
    assert response.status_code == 202, response.text
    ident = response.json()["id"]
    queue.futures[ident].result(timeout=180)
    result = client.get(f"/api/v1/agent/evaluation-runs/{ident}").json()
    assert result["status"] == "completed", result
    assert result["payload"]["acceptance_passed"], result["payload"].get("failures")
    assert len(result["payload"]["cases"]) == 60
    assert result["payload"]["metrics"]["task_success"]["total"] == 60
    assert result["payload"]["metrics"]["numerical_accuracy"]["total"] == 24
    assert result["payload"]["efficiency"]["input_tokens"] is None
    assert result["payload"]["dataset_sha256"]
    assert client.get("/api/v1/agent/evaluation-runs").json()
    with TestClient(client.app) as other:
        assert other.get(f"/api/v1/agent/evaluation-runs/{ident}").status_code == 404
        assert other.get("/api/v1/agent/evaluation-runs").json() == []
