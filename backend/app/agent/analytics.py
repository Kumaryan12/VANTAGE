"""Authorized adapters around existing Phase 1–3 services; no new risk mathematics."""

import re

from pydantic import Field
from sqlalchemy import select

from app.core.errors import AppError
from app.database.models import ForecastModel, RiskRun
from app.ml.service import explain
from app.portfolios.schemas import StrictModel
from app.risk.advanced import run_analysis
from app.risk.contracts import AnalysisRequest, AnalysisResult, StressRequest
from app.risk.records import compare_runs, get_run
from app.risk.stress_service import run_stress

from .tools import Empty, ExperimentInput, fact, register, resolve_experiment, sealed


class RiskInput(StrictModel):
    confidence: float | None = Field(None, ge=0.9, le=0.995)
    window: int | None = Field(None, ge=60, le=1260, strict=True)


class SavedRunInput(StrictModel):
    run_id: str | None = Field(None, max_length=36)


@register(
    "get_portfolio_snapshot",
    "Read the authorized captured snapshot; no broker credentials or current-to-history reconstruction.",
    Empty,
)
def portfolio_snapshot(ctx, _):
    p = ctx.portfolio
    date = p.as_of.isoformat()
    facts = [
        fact("portfolio_value", "Portfolio market value", p.total_value, "INR", date),
        fact("portfolio_cost", "Portfolio acquisition cost", p.total_cost, "INR", date),
        fact("unrealized_pnl", "Unrealized P&L", p.unrealized_pnl, "INR", date),
        fact("largest_weight", "Largest position weight", p.largest_weight, "decimal weight", date),
        fact("weight_hhi", "Position concentration HHI", p.hhi, "sum of squared weights", date),
    ]
    for h in p.holdings:
        facts.extend(
            [
                fact(
                    f"holding.{h.instrument}.weight",
                    f"{h.name} weight",
                    h.weight,
                    "decimal weight",
                    date,
                ),
                fact(f"holding.{h.instrument}.value", f"{h.name} value", h.value, "INR", date),
            ]
        )
    return sealed(
        "get_portfolio_snapshot",
        "portfolio_snapshot",
        ctx.snapshot_id,
        p.synthetic,
        date,
        {
            "holdings": [h.model_dump(mode="json") for h in p.holdings],
            "source": p.source,
            "retrieved_at": p.retrieved_at.isoformat(),
        },
        facts,
        [
            *p.warnings,
            p.price_timestamp_note,
            "A current snapshot does not establish the historical reason for a holding or allocation.",
        ],
        {
            "snapshot_id": ctx.snapshot_id,
            "source": p.source,
            "retrieved_at": p.retrieved_at.isoformat(),
        },
    )


@register(
    "get_portfolio_exposures",
    "Read validated current holding/sector weights. Allocation is not volatility contribution or a causal explanation.",
    Empty,
)
def exposures(ctx, _):
    p = ctx.portfolio
    date = p.as_of.isoformat()
    facts = [
        fact(
            f"sector.{sector}.weight",
            f"{sector} portfolio allocation",
            weight,
            "decimal weight",
            date,
        )
        for sector, weight in sorted(p.sectors.items(), key=lambda item: -item[1])
    ]
    return sealed(
        "get_portfolio_exposures",
        "portfolio_snapshot",
        ctx.snapshot_id,
        p.synthetic,
        date,
        {
            "sector_weights": p.sectors,
            "holdings_by_sector": [
                {"instrument": h.instrument, "sector": h.sector, "weight": h.weight}
                for h in p.holdings
            ],
        },
        facts,
        [
            "Sector allocations describe current portfolio weights, not risk contributions. Unknown classifications remain Unknown.",
            "Historical causes require comparable point-in-time snapshots and cannot be inferred from today's weights.",
        ],
        {"snapshot_id": ctx.snapshot_id, "source": p.source},
    )


def risk(ctx, body):
    if (
        body.confidence is not None
        and body.confidence != ctx.request.confidence
        or body.window is not None
        and body.window != ctx.request.window
    ):
        raise AppError(
            "TOOL_SCOPE",
            "Tool confidence/window must match the user's selected investigation controls.",
            403,
        )
    from app.api.advanced_risk import calculation_slot

    with calculation_slot():
        return run_analysis(
            ctx.db,
            ctx.portfolio,
            ctx.owner,
            AnalysisRequest(
                mode=ctx.request.mode,
                dataset_id=ctx.request.dataset_id,
                confidence=ctx.request.confidence,
                window=ctx.request.window,
                shrinkage=ctx.request.shrinkage,
                simulations=2000,
                seed=42,
            ),
        )


def risk_evidence(result, tool):
    date = result.metadata.valuation_as_of.isoformat()
    facts = [
        fact(
            "risk.annualized_volatility",
            "Annualized portfolio volatility",
            result.annualized_volatility,
            "decimal standard deviation / year",
            date,
        ),
        fact(
            "risk.confidence", "Risk confidence", result.parameters.confidence, "probability", date
        ),
        fact(
            "risk.sample_size",
            "Historical return observations",
            result.metadata.sample_size,
            "observations",
            date,
        ),
    ]
    for name in ("historical", "gaussian", "monte_carlo"):
        model = getattr(result.models, name)
        facts.extend(
            [
                fact(f"risk.{name}.var", f"{name} one-day VaR", model.var, "INR", date),
                fact(
                    f"risk.{name}.es",
                    f"{name} one-day Expected Shortfall",
                    model.expected_shortfall,
                    "INR",
                    date,
                ),
            ]
        )
    for asset in sorted(
        result.attribution.assets, key=lambda a: -a.component_annualized_volatility
    ):
        facts.append(
            fact(
                f"contribution.{asset.instrument}",
                f"{asset.name} annualized volatility contribution",
                asset.component_annualized_volatility,
                "decimal standard deviation / year",
                date,
            )
        )
    for sector in result.attribution.sectors:
        facts.append(
            fact(
                f"sector_risk.{sector.sector}",
                f"{sector.sector} share of portfolio volatility",
                sector.percentage_contribution,
                "decimal risk share; may be negative",
                date,
            )
        )
    facts.append(
        fact(
            "risk.reconciliation_residual",
            "Volatility attribution reconciliation residual",
            result.attribution.reconciliation_residual,
            "decimal daily standard deviation",
            date,
        )
    )
    return sealed(
        tool,
        "risk_run",
        result.run_id,
        result.portfolio.synthetic,
        date,
        {
            "parameters": result.parameters.model_dump(mode="json"),
            "attribution": result.attribution.model_dump(mode="json"),
            "models": result.models.model_dump(mode="json"),
            "metadata": result.metadata.model_dump(mode="json"),
        },
        facts,
        [
            *result.metadata.warnings,
            result.attribution.note,
            "Historical, Gaussian and Monte Carlo models have different assumptions. VaR is not a maximum possible loss or a guarantee.",
            "Current-weight retrospective returns are not historical account performance.",
        ],
        {
            "run_id": result.run_id,
            "snapshot_id": result.metadata.snapshot_id,
            "input_hash": result.metadata.input_hash,
            "source": result.provenance.model_dump(mode="json"),
        },
    )


@register(
    "calculate_portfolio_risk",
    "Calculate and save the existing Phase 2 one-day historical/Gaussian/Monte Carlo VaR and ES using selected confidence/window.",
    RiskInput,
)
def calculate_risk(ctx, body):
    return risk_evidence(risk(ctx, body), "calculate_portfolio_risk")


@register(
    "get_risk_contributions",
    "Use the existing Phase 2 covariance/Euler attribution; return signed security and sector risk contributions plus reconciliation.",
    RiskInput,
)
def risk_contributions(ctx, body):
    return risk_evidence(risk(ctx, body), "get_risk_contributions")


@register(
    "get_saved_risk_run",
    "Read an owned selected saved analytical risk run, preserving original dates/settings.",
    SavedRunInput,
)
def saved_risk(ctx, body):
    if ctx.request.run_ids and body.run_id and body.run_id not in ctx.request.run_ids:
        raise AppError("TOOL_SCOPE", "Risk run must belong to the selected context.", 403)
    ident = body.run_id or (ctx.request.run_ids[0] if ctx.request.run_ids else None)
    if ident is None:
        row = ctx.db.scalar(
            select(RiskRun)
            .where(
                RiskRun.owner == ctx.owner,
                RiskRun.kind == "analysis",
                RiskRun.result["portfolio"]["mode"].as_string() == ctx.request.mode,
            )
            .order_by(RiskRun.created_at.desc())
            .limit(1)
        )
        if row is None:
            raise AppError(
                "RISK_RUN_MISSING", "No authorized saved analytical risk run is available.", 404
            )
        ident = row.id
    result = get_run(ctx.db, ident, ctx.owner).result
    if not isinstance(result, AnalysisResult):
        raise AppError(
            "RISK_RUN_KIND",
            "Select a Phase 2 analytical risk run; scenarios/legacy runs are distinct.",
        )
    if result.portfolio.mode != ctx.request.mode:
        raise AppError("TOOL_SCOPE", "Saved run has a different source mode.", 403)
    return risk_evidence(result, "get_saved_risk_run")


@register(
    "compare_risk_runs",
    "Compare only explicitly selected authorized saved runs, retaining methodology/confidence/window warnings.",
    Empty,
)
def compare_saved(ctx, _):
    if len(ctx.request.run_ids) < 2:
        raise AppError(
            "COMPARABLE_SNAPSHOTS_REQUIRED",
            "Select at least two accessible saved runs; a historical cause cannot be established from one current snapshot.",
            422,
        )
    result = compare_runs(ctx.db, ctx.request.run_ids, ctx.owner)
    data = result.model_dump(mode="json")
    facts = []
    for row in data["rows"]:
        for key in (
            "historical_var",
            "historical_es",
            "stress_pnl",
            "var_delta",
            "es_delta",
            "pnl_delta",
        ):
            facts.append(
                fact(
                    f"{row['id']}.{key}",
                    f"{row['id'][:8]} {key.replace('_', ' ')}",
                    row[key],
                    "INR",
                    str(row["created_at"]),
                )
            )
    return sealed(
        "compare_risk_runs",
        "risk_comparison",
        result.baseline_id,
        ctx.request.mode == "demo",
        "See each saved run",
        data,
        facts,
        [
            *result.warnings,
            "Changes are descriptive comparisons; snapshots do not identify causal reasons.",
        ],
        {"run_ids": ctx.request.run_ids},
    )


def bound_scenario(ctx):
    if ctx.request.scenario:
        if ctx.request.scenario.kind != "hypothetical":
            raise AppError(
                "SCENARIO_SCOPE",
                "Agent scenarios are direct hypothetical shocks; historical replay stays in the controlled stress interface.",
            )
        return ctx.request.scenario
    question = ctx.request.question.lower()
    values = re.findall(
        r"(?:fall\w*|drop\w*|declin\w*|down|shock\w*|crash\w*)[^\d%]{0,25}(\d+(?:\.\d+)?)\s*(?:%|percent)",
        question,
    )
    if len(values) != 1:
        raise AppError(
            "SCENARIO_REQUIRED",
            "Specify one unambiguous sector/market fall percentage or supply a typed scenario. No shock is inferred from vague wording.",
            422,
        )
    shock = -float(values[0]) / 100
    known = {s.lower(): s for s in ctx.portfolio.sectors if s != "Unknown"}
    if "technology" in known and re.search(r"\btech(?:nology)?\b", question):
        sector = "Technology"
    else:
        sector = next((label for key, label in known.items() if key in question), None)
    parameters = {
        "mode": ctx.request.mode,
        "dataset_id": ctx.request.dataset_id,
        "confidence": ctx.request.confidence,
        "window": ctx.request.window,
        "kind": "hypothetical",
        "name": "User-requested direct hypothetical shock",
    }
    if sector:
        parameters["sector_shocks"] = {sector: shock}
    elif any(
        term in question
        for term in (
            "whole portfolio",
            "all holdings",
            "all stocks",
            "market falls",
            "market drops",
        )
    ):
        parameters["market_shock"] = shock
    else:
        raise AppError(
            "SECTOR_REQUIRED",
            "Identify a known classified sector or explicit broad-market shock. Unknown factor exposures are not invented.",
            422,
        )
    return StressRequest.model_validate(parameters)


@register(
    "run_stress_scenario",
    "Run only the user's explicit hypothetical scenario through the existing Phase 2 stress engine; never a prediction or trade.",
    Empty,
)
def stress_scenario(ctx, _):
    from app.api.advanced_risk import calculation_slot

    parameters = bound_scenario(ctx)
    with calculation_slot():
        result = run_stress(ctx.db, ctx.portfolio, ctx.owner, parameters)
    date = result.metadata.valuation_as_of.isoformat()
    facts = [
        fact(f"stress.{key}", label, getattr(result, key), unit, date)
        for key, label, unit in (
            ("value_before", "Scenario starting value", "INR"),
            ("value_after", "Scenario ending value", "INR"),
            ("pnl", "Hypothetical scenario P&L", "INR"),
            ("loss", "Hypothetical scenario loss", "INR"),
            ("portfolio_return", "Hypothetical portfolio return", "decimal return"),
            ("pnl_reconciliation_residual", "P&L contribution reconciliation residual", "INR"),
        )
    ]
    for sector in result.sectors:
        facts.append(
            fact(
                f"stress.sector.{sector.sector}.pnl",
                f"{sector.sector} scenario P&L",
                sector.pnl,
                "INR",
                date,
            )
        )
    for asset in result.assets:
        facts.append(
            fact(
                f"stress.asset.{asset.instrument}.pnl",
                f"{asset.name} scenario P&L",
                asset.pnl,
                "INR",
                date,
            )
        )
    return sealed(
        "run_stress_scenario",
        "risk_run",
        result.run_id,
        result.portfolio.synthetic,
        date,
        {
            "parameters": parameters.model_dump(mode="json"),
            "assets": [a.model_dump(mode="json") for a in result.assets],
            "sectors": [s.model_dump(mode="json") for s in result.sectors],
        },
        facts,
        [
            *result.metadata.warnings,
            *result.assumptions,
            "This is the user's direct hypothetical shock, not a forecast, causal estimate, factor model or investment recommendation.",
        ],
        {
            "run_id": result.run_id,
            "snapshot_id": result.metadata.snapshot_id,
            "input_hash": result.metadata.input_hash,
        },
    )


@register(
    "get_model_explanation",
    "Reload the saved LightGBM model for an owned experiment and explain its actual latest scored prediction. SHAP is not causal.",
    ExperimentInput,
)
def model_explanation(ctx, body):
    exp = resolve_experiment(ctx, body.experiment_id)
    model = ctx.db.scalar(
        select(ForecastModel).where(
            ForecastModel.owner == ctx.owner,
            ForecastModel.experiment_id == exp.id,
            ForecastModel.kind == "lightgbm",
        )
    )
    if model is None:
        raise AppError(
            "MODEL_MISSING", "No saved LightGBM model is available for this experiment.", 404
        )
    result = explain(ctx.db, model)
    facts = [
        fact(
            f"explanation.{key}",
            key.replace("_", " "),
            getattr(result, key),
            "decimal variance",
            str(result.target),
        )
        for key in (
            "forecast_variance",
            "raw_variance",
            "base_variance",
            "floor_adjustment",
            "reconstruction_residual",
        )
    ]
    return sealed(
        "get_model_explanation",
        "forecast_model",
        model.id,
        exp.data_info["synthetic"],
        str(result.target),
        {
            "origin": str(result.origin),
            "target": str(result.target),
            "features": result.features[:10],
            "training_window_id": result.training_window_id,
        },
        facts,
        [
            result.note,
            "A prediction explanation does not establish why one model's future predictive loss differs from another.",
        ],
        {"experiment_id": exp.id, "model_id": model.id, "dataset_hash": exp.dataset_hash},
    )
