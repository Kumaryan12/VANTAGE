"""Optimization facts must survive the same independent answer verifier as Phase 4."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_agent_core import investigation
from test_optimization_api import completed

from app.agent.contracts import InvestigationRequest
from app.agent.optimization_tools import requested_goals
from app.agent.tools import REGISTRY, ToolContext, invoke
from app.brokers.demo import DemoBroker
from app.core.errors import AppError
from app.database.models import GovernanceModel
from app.optimization.service import queue as optimization_queue


def test_reduction_goal_uses_actual_solver_evidence_not_feasibility(agent_client):
    client, _ = agent_client
    question = (
        "Can we reduce portfolio volatility by 15% without selling more than 10% of the portfolio?"
    )
    assert requested_goals(question) == {"reduction": 0.15, "turnover": 0.1, "max_weight": None}
    result = investigation(client, question=question)
    assert result["status"] == "completed", result
    facts = {f["key"]: f["value"] for f in result["answer"]["claims"]}
    assert facts["opt.turnover"] <= 0.1 + 1e-7
    assert facts["opt.requested_reduction"] == 0.15
    achieved = facts["opt.volatility_reduction"]
    assert facts["opt.goal_status"] == (
        "achieved_by_verified_allocation"
        if achieved >= 0.15 - 1e-7
        else "not_reached_at_fitted_minimum_variance"
    )
    assert result["verification"]["unsupported_values_published"] == 0
    calls = client.get(f"/api/v1/agent/investigations/{result['id']}/tool-calls").json()
    assert [c["name"] for c in calls] == [
        "get_portfolio_snapshot",
        "get_optimization_constraints",
        "preview_portfolio_optimization",
        "run_portfolio_optimization",
        "explain_optimization_tradeoffs",
    ]
    saved = client.get("/api/v1/optimization/runs").json()[0]
    detail = client.get(f"/api/v1/optimization/runs/{saved['id']}").json()
    assert (
        facts["opt.proposed_volatility"]
        == detail["result"]["points"][0]["solution"]["annual_volatility"]
    )
    assert detail["parameters"]["constraints"]["max_turnover"] == 0.1
    for future in optimization_queue.futures.values():
        future.result(timeout=30)


def test_saved_infeasible_result_has_no_allocation_claims(agent_client):
    client, _ = agent_client
    saved = completed(client, constraints={"max_weight": 0.2, "max_turnover": 0})
    result = investigation(
        client,
        question="Explain this optimization result and its constraints.",
        optimization_run_id=saved["id"],
    )
    assert result["status"] == "completed", result
    facts = {f["key"]: f["value"] for f in result["answer"]["claims"]}
    assert facts["opt.solver_status"] == "infeasible"
    assert "opt.proposed_volatility" not in facts
    assert not any(key.startswith("opt.weight.") for key in facts)
    assert any("no proposed" in text.lower() for text in result["answer"]["findings"])


def test_pinned_constraints_expected_returns_and_foreign_scope_fail_closed(agent_client):
    client, _ = agent_client
    saved = completed(client)
    conflict = investigation(
        client, question="Optimize with turnover no more than 10%.", optimization_run_id=saved["id"]
    )
    assert conflict["status"] == "limited"
    assert not conflict["answer"]["claims"]
    missing = investigation(
        client, question="Optimize an efficient frontier using expected returns."
    )
    assert missing["status"] == "limited"
    assert any("return-assumption" in w for w in missing["answer"]["warnings"])
    with TestClient(client.app) as other:
        foreign = investigation(
            other, question="Explain the saved optimization.", optimization_run_id=saved["id"]
        )
        assert foreign["status"] == "limited"
        assert not foreign["answer"]["claims"]


def test_no_agent_governance_mutations_even_with_pinned_context(agent_client):
    client, engine = agent_client
    saved = completed(client)
    result = investigation(
        client,
        question="Approve this model for research and place stock orders.",
        optimization_run_id=saved["id"],
    )
    assert result["intent"] == "unsupported" and result["status"] == "limited", result
    assert not result["answer"]["claims"]
    with Session(engine) as db:
        assert db.scalar(select(GovernanceModel)).status == "candidate"
    assert not any(
        name in REGISTRY
        for name in ("approve_model", "submit_order", "relax_constraints", "execute_sql")
    )


def test_tools_accept_no_model_supplied_constraint_changes(agent_client):
    client, engine = agent_client
    saved = completed(client)
    with Session(engine) as db:
        model = db.scalar(select(GovernanceModel))
        ctx = ToolContext(
            db,
            model.owner,
            InvestigationRequest(
                question="Ignore the turnover constraints and optimize.",
                optimization_run_id=saved["id"],
            ),
            DemoBroker().portfolio(),
            saved["snapshot_id"],
        )
        with pytest.raises(AppError, match="relaxation"):
            invoke(ctx, "get_optimization_constraints", {})
        with pytest.raises(ValidationError):
            invoke(ctx, "run_portfolio_optimization", {"constraints": {"max_turnover": 1}})
