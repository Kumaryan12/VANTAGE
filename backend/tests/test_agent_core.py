import json
import threading
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent.contracts import WorkflowState
from app.agent.provider import OpenAIProvider, ProviderTurn
from app.agent.service import queue
from app.agent.tools import REGISTRY, fact, sealed
from app.agent.verification import default_selection, verify_and_compose
from app.core.config import settings
from app.core.errors import AppError
from app.main import app
from app.ml.service import queue as research_queue


def completed_research(client):
    response = client.post("/api/v1/ml/backtest", json={"max_trees": 40, "search_candidates": 2})
    assert response.status_code == 202, response.text
    ident = response.json()["id"]
    research_queue.futures[ident].result(timeout=30)
    assert client.get(f"/api/v1/ml/experiments/{ident}").json()["status"] == "completed"
    return ident


def investigation(client, **kwargs):
    response = client.post(
        "/api/v1/agent/investigate",
        json={
            "question": "Compare forecasting models on QLIKE and explain their limitations.",
            **kwargs,
        },
    )
    assert response.status_code == 202, response.text
    ident = response.json()["id"]
    queue.futures[ident].result(timeout=30)
    detail = client.get(f"/api/v1/agent/investigations/{ident}")
    assert detail.status_code == 200, detail.text
    return detail.json()


def test_first_verified_model_comparison_and_private_trace(agent_client):
    client, _ = agent_client
    exp = completed_research(client)
    result = investigation(client, experiment_id=exp)
    assert result["status"] == "completed", result
    answer = result["answer"]
    assert answer["execution_mode"] == "Deterministic demonstration"
    claims = {f["key"]: f for f in answer["claims"]}
    actual = client.get(f"/api/v1/ml/comparison?experiment_id={exp}").json()
    for row in actual["models"]:
        assert claims[row["kind"] + ".qlike"]["value"] == row["metrics"]["qlike"]
    assert claims["lowest_qlike_model"]["value"] == "rolling"
    assert claims["matched_observations"]["value"] == 100
    assert claims["high_regime_observations"]["value"] == 0
    assert any("intervals include zero" in s for s in answer["findings"])
    assert any("current snapshot weights" in s for s in answer["warnings"])
    assert any("SYNTHETIC" in s for s in answer["warnings"])
    assert result["verification"]["unsupported_values_published"] == 0
    trace = client.get(f"/api/v1/agent/investigations/{result['id']}/trace").json()
    assert len(trace) <= 24 and trace[-1]["kind"] == "compose"
    calls = client.get(f"/api/v1/agent/investigations/{result['id']}/tool-calls").json()
    assert [c["name"] for c in calls] == ["list_research_experiments", "compare_forecasting_models"]
    evidence = client.get(f"/api/v1/agent/investigations/{result['id']}/evidence").json()
    assert evidence[-1]["source_id"] == exp
    assert evidence[-1]["provenance"]["runtime"]["git_commit"]
    with TestClient(app) as stranger:
        for suffix in ("", "/trace", "/evidence", "/tool-calls"):
            assert (
                stranger.get(f"/api/v1/agent/investigations/{result['id']}{suffix}").status_code
                == 404
            )
        assert (
            stranger.post(f"/api/v1/agent/investigations/{result['id']}/cancel").status_code == 404
        )
        other = investigation(stranger, experiment_id=exp)
        assert other["status"] == "limited" and not other["answer"]["claims"]
    assert client.get("/api/v1/agent/investigations").json()


def test_missing_research_no_fallback_and_no_provider(agent_client):
    client, _ = agent_client
    assert client.get("/api/v1/agent/status").json()["configured"] is False
    result = investigation(client)
    assert result["status"] == "limited"
    assert any("No completed research" in w for w in result["answer"]["warnings"])
    assert not result["answer"]["claims"]
    response = client.post(
        "/api/v1/agent/investigate",
        json={
            "question": "Compare forecasting models",
            "engine": "llm",
            "external_data_consent": True,
        },
    )
    assert response.status_code == 503 and response.json()["error"]["code"] == "AI_NOT_CONFIGURED"
    assert (
        client.post(
            "/api/v1/agent/investigate", json={"question": "Compare models", "engine": "llm"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/agent/investigate", json={"question": "Compare models", "max_tools": 999}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/agent/investigate",
            json={"question": "Compare models"},
            headers={"Origin": "https://evil.test"},
        ).status_code
        == 403
    )


def test_verifier_rejects_wrong_values_units_dates_and_hash():
    evidence = sealed(
        "test",
        "snapshot",
        "snapshot-id",
        True,
        "2026-10-23",
        {},
        [fact("value", "Portfolio value", 100.0, "INR", "2026-10-23")],
        [],
    )
    state = WorkflowState(intent="portfolio", evidence=[evidence])
    selection = default_selection(state.evidence)
    assert verify_and_compose(state, selection, "demo").claims[0].value == 100
    for change in (
        {"value": 101.0},
        {"unit": "USD"},
        {"as_of": "2026-10-22"},
        {"fact_key": "made_up"},
        {"evidence_id": "foreign"},
    ):
        changed = selection.model_copy(deep=True)
        changed.claims[0] = changed.claims[0].model_copy(update=change)
        with pytest.raises(AppError):
            verify_and_compose(state, changed, "demo")
    state.evidence[0].facts[0].value = 999
    with pytest.raises(AppError, match="changed before"):
        verify_and_compose(state, selection, "demo")


def test_mock_provider_calls_approved_tool_then_uses_verified_selection(agent_client, monkeypatch):
    client, _ = agent_client
    completed_research(client)
    monkeypatch.setattr(settings(), "openai_api_key", "sk-test-provider-key-private")

    class MockProvider:
        def next(self, question, evidence, tools, errors, remaining_seconds):
            if not evidence:
                return ProviderTurn(
                    tool="compare_forecasting_models",
                    arguments={},
                    input_tokens=20,
                    output_tokens=8,
                )
            return ProviderTurn(
                final=default_selection(evidence), input_tokens=50, output_tokens=20
            )

    monkeypatch.setattr("app.agent.service.configured_provider", MockProvider)
    result = investigation(client, engine="llm", external_data_consent=True)
    assert result["status"] == "completed", result
    assert result["usage"]["input_tokens"] == 70
    assert result["usage"]["estimated_cost_usd"] is None
    assert "sk-test-provider" not in json.dumps(result)


def test_provider_unauthorized_actions_and_invalid_financial_values_rejected(
    agent_client, monkeypatch
):
    client, _ = agent_client
    completed_research(client)
    monkeypatch.setattr(settings(), "openai_api_key", "private-configured-test-key")

    class Forbidden:
        def next(self, *args):
            return ProviderTurn(tool="execute_sql", arguments={"sql": "SELECT secrets"})

    monkeypatch.setattr("app.agent.service.configured_provider", Forbidden)
    result = investigation(client, engine="llm", external_data_consent=True)
    assert result["status"] == "failed" and result["error"]["code"] == "TOOL_NOT_ALLOWED"

    class Fabricated:
        def next(self, question, evidence, *args):
            if not evidence:
                return ProviderTurn(tool="compare_forecasting_models", arguments={})
            selection = default_selection(evidence)
            selection.claims[0].value = "lightgbm"
            return ProviderTurn(final=selection)

    monkeypatch.setattr("app.agent.service.configured_provider", Fabricated)
    result = investigation(client, engine="llm", external_data_consent=True)
    assert result["status"] == "failed" and result["answer"] is None
    assert result["error"]["code"] == "NUMERICAL_VERIFICATION"


def test_budgets_cancellation_and_tool_timeout(agent_client, monkeypatch):
    client, _ = agent_client
    result = investigation(client, max_steps=4)
    assert result["status"] == "failed" and result["error"]["code"] == "GRAPH_STEP_LIMIT"
    result = investigation(client, max_tools=1)
    assert result["status"] == "failed" and result["error"]["code"] == "TOOL_CALL_LIMIT"
    entered = threading.Event()
    release = threading.Event()
    original = queue.run_tool

    def slow(*args):
        entered.set()
        release.wait(2)
        return original(*args)

    monkeypatch.setattr(queue, "run_tool", slow)
    response = client.post(
        "/api/v1/agent/investigate", json={"question": "Compare forecasting models"}
    )
    ident = response.json()["id"]
    assert entered.wait(3)
    assert (
        client.post(
            "/api/v1/agent/investigate", json={"question": "Compare forecasting models"}
        ).status_code
        == 503
    )
    client.post(f"/api/v1/agent/investigations/{ident}/cancel")
    release.set()
    queue.futures[ident].result(timeout=5)
    assert client.get(f"/api/v1/agent/investigations/{ident}").json()["status"] == "cancelled"
    queue.tool_executor.submit(lambda: None).result(timeout=5)
    monkeypatch.setitem(
        REGISTRY,
        "list_research_experiments",
        replace(REGISTRY["list_research_experiments"], timeout_seconds=0.01),
    )
    release.clear()
    response = client.post(
        "/api/v1/agent/investigate", json={"question": "Compare forecasting models"}
    )
    ident = response.json()["id"]
    queue.futures[ident].result(timeout=5)
    release.set()
    assert (
        client.get(f"/api/v1/agent/investigations/{ident}").json()["error"]["code"]
        == "TOOL_TIMEOUT"
    )


def test_openai_transport_schema_redaction_and_retry(monkeypatch):
    monkeypatch.setattr(settings(), "openai_api_key", "sk-config-secret-private")
    payloads = []

    def handler(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        assert "sk-config-secret" not in json.dumps(payload)
        if len(payloads) == 1:
            return httpx.Response(429, json={"error": "limited"})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "name": "compare_forecasting_models",
                        "arguments": '{"experiment_id":null}',
                    }
                ],
                "usage": {"input_tokens": 12, "output_tokens": 4},
            },
        )

    original = httpx.Client
    monkeypatch.setattr(
        "app.agent.provider.httpx.Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = OpenAIProvider().next(
        "Compare models sk-config-secret-private", [], list(REGISTRY.values()), [], 20
    )
    assert result.tool == "compare_forecasting_models" and result.input_tokens == 12
    assert len(payloads) == 2
    assert payloads[-1]["store"] is False
    assert payloads[-1]["tools"][1]["parameters"]["additionalProperties"] is False


def test_provider_failure_and_scope_mismatch_do_not_publish_answer(agent_client, monkeypatch):
    client, _ = agent_client
    monkeypatch.setattr(settings(), "openai_api_key", "sk-test-configured-private")

    class UnavailableProvider:
        def next(self, *args):
            raise AppError(
                "AI_PROVIDER_TIMEOUT", "Mocked transport timeout after bounded retry.", 504
            )

    monkeypatch.setattr("app.agent.service.configured_provider", UnavailableProvider)
    result = investigation(client, engine="llm", external_data_consent=True)
    assert result["status"] == "failed" and result["answer"] is None
    assert result["error"]["code"] == "AI_PROVIDER_TIMEOUT"

    class OutOfScope:
        def next(self, *args):
            return ProviderTurn(tool="get_portfolio_snapshot", arguments={})

    monkeypatch.setattr("app.agent.service.configured_provider", OutOfScope)
    result = investigation(
        client,
        question="Find liquidity risks in uploaded documents.",
        engine="llm",
        external_data_consent=True,
    )
    assert result["status"] == "failed" and result["error"]["code"] == "TOOL_NOT_ALLOWED"
    calls = client.get(f"/api/v1/agent/investigations/{result['id']}/tool-calls").json()
    assert calls[0]["status"] == "denied"
