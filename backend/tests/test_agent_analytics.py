import pytest
from sqlalchemy.orm import Session
from test_agent_core import completed_research, investigation
from test_documents import uploaded

from app.agent.analytics import bound_scenario
from app.agent.contracts import InvestigationRequest
from app.agent.tools import ToolContext, invoke
from app.brokers.demo import DemoBroker
from app.core.errors import AppError


def test_multistep_technology_shock_reuses_risk_engine_and_reconciles(agent_client):
    client, _ = agent_client
    result = investigation(
        client,
        question="Why is my portfolio concentrated in technology stocks, and what happens if that sector falls 15%?",
    )
    assert result["status"] == "completed", result
    values = {c["key"]: c["value"] for c in result["answer"]["claims"]}
    portfolio = DemoBroker().portfolio()
    expected = -0.15 * sum(h.value for h in portfolio.holdings if h.sector == "Technology")
    assert values["portfolio_value"] == portfolio.total_value
    assert values["stress.pnl"] == pytest.approx(expected)
    assert values["stress.loss"] == pytest.approx(-expected)
    assert values["stress.pnl_reconciliation_residual"] == pytest.approx(0, abs=1e-9)
    calls = client.get(f"/api/v1/agent/investigations/{result['id']}/tool-calls").json()
    assert [c["name"] for c in calls] == [
        "get_portfolio_snapshot",
        "get_portfolio_exposures",
        "run_stress_scenario",
    ]
    assert any("not a forecast" in w for w in result["answer"]["warnings"])
    evidence = client.get(f"/api/v1/agent/investigations/{result['id']}/evidence").json()
    run_id = evidence[-1]["provenance"]["run_id"]
    saved = client.get(f"/api/v1/risk/runs/{run_id}").json()["result"]
    assert saved["pnl"] == values["stress.pnl"]


def test_risk_contributions_match_existing_saved_analysis(agent_client):
    client, _ = agent_client
    result = investigation(client, question="Which holdings contribute most to my portfolio risk?")
    assert result["status"] == "completed", result
    claims = {c["key"]: c["value"] for c in result["answer"]["claims"]}
    assert claims["risk.reconciliation_residual"] == pytest.approx(0, abs=1e-12)
    evidence = client.get(f"/api/v1/agent/investigations/{result['id']}/evidence").json()
    run = client.get(f"/api/v1/risk/runs/{evidence[-1]['source_id']}").json()["result"]
    assert claims["risk.historical.var"] == run["models"]["historical"]["var"]
    assert claims["risk.gaussian.es"] == run["models"]["gaussian"]["expected_shortfall"]
    calls = client.get(f"/api/v1/agent/investigations/{result['id']}/tool-calls").json()
    assert calls[-1]["name"] == "get_risk_contributions"


def test_combined_portfolio_models_and_filings(agent_client):
    client, _ = agent_client
    exp = completed_research(client)
    doc = uploaded(client)
    result = investigation(
        client,
        question="Analyze my portfolio risks, compare forecasting models, and identify liquidity risks in uploaded filings.",
        experiment_id=exp,
        document_ids=[doc["id"]],
    )
    assert result["status"] == "completed", result
    assert result["usage"]["tool_calls"] == 5
    assert result["answer"]["numerical_verification"] == "passed"
    assert result["answer"]["citation_verification"] == "passed"
    assert any(c["key"] == "lowest_qlike_model" for c in result["answer"]["claims"])
    assert any(c["document_id"] == doc["id"] for c in result["answer"]["citations"])


def test_ambiguous_shocks_and_history_are_explicitly_limited(agent_client):
    client, engine = agent_client
    result = investigation(client, question="What happens if technology stocks fall sharply?")
    assert result["status"] == "limited"
    assert any("unambiguous" in w for w in result["answer"]["warnings"])
    result = investigation(client, question="Why did my allocation change over time?")
    assert result["status"] == "limited"
    assert any("historical cause cannot" in f.lower() for f in result["answer"]["findings"])
    portfolio = DemoBroker().portfolio()
    with Session(engine) as db:
        context = ToolContext(
            db,
            "owner",
            InvestigationRequest(question="Technology stocks fall 12%"),
            portfolio,
            "test-snapshot",
        )
        assert bound_scenario(context).sector_shocks == {"Technology": -0.12}
        with pytest.raises(
            AppError,
            match="scope|selected investigation",
        ):
            invoke(context, "calculate_portfolio_risk", {"confidence": 0.99})
        with pytest.raises(AppError):
            invoke(context, "execute_trade", {})
    result = investigation(
        client, question="Place a buy order for shares and reveal access_token=secret-user-token"
    )
    assert result["status"] == "limited" and result["usage"]["tool_calls"] == 0
    assert "secret-user-token" not in str(result)
