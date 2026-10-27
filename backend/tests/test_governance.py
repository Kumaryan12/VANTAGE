from fastapi.testclient import TestClient
from test_optimization_api import completed

from app.governance.contracts import REVIEW_AREAS
from app.optimization.service import queue


def test_explicit_research_review_transitions_require_evidence_and_human_ack(agent_client):
    client, _ = agent_client
    result = completed(client)
    model_id = result["result"]["governance_model_id"]
    initial = client.get(f"/api/v1/governance/models/{model_id}").json()
    assert initial["status"] == "candidate"
    assert initial["current_validation"]["synthetic"] is True
    assert initial["current_validation"]["validation_ready"] is False
    body = {
        "status": "approved_research",
        "human_review": True,
        "research_only": True,
        "rationale": "Reviewed this synthetic model solely for local methodological research.",
    }
    assert client.post(f"/api/v1/governance/models/{model_id}/review", json=body).status_code == 409
    body["status"] = "under_review"
    assert (
        client.post(f"/api/v1/governance/models/{model_id}/review", json=body).json()["status"]
        == "under_review"
    )
    body["status"] = "validated"
    body["assessments"] = {
        area: "Synthetic methodological assessment only; real-market evidence is unavailable and not claimed."
        for area in REVIEW_AREAS
    }
    assert client.post(f"/api/v1/governance/models/{model_id}/review", json=body).status_code == 409
    reproduction = client.post(f"/api/v1/optimization/runs/{result['id']}/reproduce")
    queue.futures[reproduction.json()["id"]].result(timeout=30)
    validated = client.post(f"/api/v1/governance/models/{model_id}/review", json=body)
    assert validated.status_code == 200, validated.text
    assert validated.json()["status"] == "validated"
    body["status"] = "approved_research"
    body["assessments"] = {}
    approved = client.post(f"/api/v1/governance/models/{model_id}/review", json=body)
    assert approved.status_code == 200, approved.text
    assert approved.json()["payload"]["approval_scope"] == "methodology_research"
    body["approval_scope"] = "real_market_use"
    assert client.post(f"/api/v1/governance/models/{model_id}/review", json=body).status_code == 422
    body["approval_scope"] = "methodology_research"
    body["status"] = "retired"
    body["human_review"] = False
    assert client.post(f"/api/v1/governance/models/{model_id}/review", json=body).status_code == 422
    body["human_review"] = True
    assert (
        client.post(f"/api/v1/governance/models/{model_id}/review", json=body).json()["status"]
        == "retired"
    )
    body["status"] = "candidate"
    assert client.post(f"/api/v1/governance/models/{model_id}/review", json=body).status_code == 409
    events = client.get(f"/api/v1/governance/events?model_id={model_id}").json()
    assert len(events) == 5
    assert events[0]["payload"]["reviewer_session"]
    with TestClient(client.app) as other:
        assert other.get(f"/api/v1/governance/models/{model_id}").status_code == 404
        assert (
            other.post(f"/api/v1/governance/models/{model_id}/review", json=body).status_code == 404
        )
        assert other.get(f"/api/v1/governance/events?model_id={model_id}").status_code == 404
        assert other.get("/api/v1/governance/models").json() == []
