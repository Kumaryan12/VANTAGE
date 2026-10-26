import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.database.models import RiskRun
from app.portfolios.schemas import RiskResult
from app.risk.advanced import run_analysis
from app.risk.artifacts import MODEL_VERSION, owned_run, replay_inputs
from app.risk.contracts import (
    AnalysisRequest,
    AnalysisResult,
    ComparisonRow,
    ReplayResult,
    RunComparison,
    RunSummary,
    SavedRun,
    StressRequest,
    StressResult,
)
from app.risk.stress_service import run_stress


def parsed_result(run: RiskRun):
    if run.kind == "analysis":
        return AnalysisResult.model_validate(run.result)
    if run.kind == "stress":
        return StressResult.model_validate(run.result)
    return RiskResult.model_validate(run.result)


def summary(run: RiskRun) -> RunSummary:
    result = parsed_result(run)
    if run.schema_version == 1:
        return RunSummary(
            id=run.id,
            kind="legacy",
            mode=result.mode,
            name="Phase 1 historical risk",
            created_at=run.created_at,
            confidence=result.confidence,
            window=result.requested_window,
            sample_size=result.sample_size,
            portfolio_value=result.historical_var_amount / result.historical_var
            if result.historical_var
            else None,
            historical_var=result.historical_var_amount,
            historical_es=None,
            stress_pnl=None,
            replayable=False,
        )
    return RunSummary(
        id=run.id,
        kind=run.kind,
        mode=result.portfolio.mode,
        name=result.name if run.kind == "stress" else "Historical / Gaussian / Monte Carlo",
        created_at=run.created_at,
        confidence=result.parameters.confidence,
        window=result.parameters.window,
        sample_size=result.metadata.sample_size,
        portfolio_value=result.portfolio.total_value,
        historical_var=result.models.historical.var if run.kind == "analysis" else None,
        historical_es=result.models.historical.expected_shortfall
        if run.kind == "analysis"
        else None,
        stress_pnl=result.pnl if run.kind == "stress" else None,
        replayable=bool(run.snapshot_id and run.input_artifact_id),
    )


def list_runs(db: Session, owner: str, limit: int, offset: int, mode: str | None):
    # Legacy records are retained and individually readable but lack immutable replay inputs.
    query = select(RiskRun).where(RiskRun.owner == owner, RiskRun.schema_version == 2)
    if mode is not None:
        query = query.where(RiskRun.result["portfolio"]["mode"].as_string() == mode)
    records = db.scalars(
        query.order_by(RiskRun.created_at.desc(), RiskRun.id.desc()).limit(limit).offset(offset)
    ).all()
    return [summary(run) for run in records]


def get_run(db: Session, run_id: str, owner: str):
    run = owned_run(db, run_id, owner)
    return SavedRun(
        id=run.id,
        input_hash=run.input_hash,
        replayable=bool(run.snapshot_id and run.input_artifact_id),
        result=parsed_result(run),
    )


def compare_runs(db: Session, run_ids: list[str], owner: str):
    if len(set(run_ids)) != len(run_ids):
        raise AppError("DUPLICATE_RUN", "Choose distinct run IDs.")
    runs = [owned_run(db, run_id, owner) for run_id in run_ids]
    if len({run.kind for run in runs}) != 1 or any(run.schema_version != 2 for run in runs):
        raise AppError(
            "INCOMPARABLE_RUNS", "Compare Phase 2 analyses together or stress scenarios together."
        )
    rows = [summary(run) for run in runs]
    baseline = rows[0]
    warnings = [
        "Differences are descriptive model outputs, not predictive superiority or changes-in-risk attribution."
    ]
    results = [parsed_result(run) for run in runs]
    if len({run.snapshot_id for run in runs}) > 1:
        warnings.append(
            "Portfolio snapshots differ; monetary risk changes combine portfolio value, weights and data effects."
        )
    if len({(row.confidence, row.window, row.sample_size) for row in rows}) > 1:
        warnings.append(
            "Confidence, estimation window, or sample size differs between selected runs."
        )
    if (
        runs[0].kind == "stress"
        and len(
            {
                (
                    r.scenario_kind,
                    str(r.parameters.start),
                    str(r.parameters.end),
                    r.parameters.scenario_id,
                )
                for r in results
            }
        )
        > 1
    ):
        warnings.append(
            "Stress windows or scenario types differ; P&L differences are not horizon-normalized."
        )
    return RunComparison(
        baseline_id=baseline.id,
        rows=[
            ComparisonRow(
                **row.model_dump(),
                var_delta=row.historical_var - baseline.historical_var
                if row.historical_var is not None
                else None,
                es_delta=row.historical_es - baseline.historical_es
                if row.historical_es is not None
                else None,
                pnl_delta=row.stress_pnl - baseline.stress_pnl
                if row.stress_pnl is not None
                else None,
            )
            for row in rows
        ],
        warnings=warnings,
    )


def numerically_equal(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(numerically_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(numerically_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-10)
    return a == b


def replay_run(db: Session, run_id: str, owner: str):
    original = owned_run(db, run_id, owner)
    if original.schema_version != 2:
        raise AppError("REPLAY_UNAVAILABLE", "Legacy Phase 1 runs do not contain replay inputs.")
    old = parsed_result(original)
    if old.metadata.model_version != MODEL_VERSION:
        raise AppError(
            "MODEL_VERSION_UNAVAILABLE",
            "The saved methodology version is not implemented by this runtime; no silent model migration.",
            409,
        )
    portfolio, payload = replay_inputs(db, original, owner)
    if original.kind == "analysis":
        result = run_analysis(
            db,
            portfolio,
            owner,
            AnalysisRequest.model_validate(original.parameters),
            replay_payload=payload,
        )
        fields = (
            "models",
            "covariance",
            "correlation",
            "covariance_diagnostics",
            "attribution",
            "simulation",
            "expected_daily_return",
            "daily_volatility",
            "annualized_volatility",
            "sample_annualized_volatility",
        )
    else:
        result = run_stress(
            db,
            portfolio,
            owner,
            StressRequest.model_validate(original.parameters),
            replay_payload=payload,
        )
        fields = (
            "value_before",
            "value_after",
            "portfolio_return",
            "pnl",
            "loss",
            "assets",
            "sectors",
            "path",
            "reference_risk",
        )
    old_json, new_json = old.model_dump(mode="json"), result.model_dump(mode="json")
    return ReplayResult(
        original_run_id=original.id,
        replayed_run_id=result.run_id,
        input_hash_matches=original.input_hash == result.metadata.input_hash,
        numerical_results_match=all(
            numerically_equal(old_json[field], new_json[field]) for field in fields
        ),
        result=result,
        note="Recomputed from immutable saved snapshots and dated price inputs; no broker/provider request. Exact reproducibility requires the recorded numerical runtime; cross-runtime differences are checked with rtol=1e-12, atol=1e-10.",
    )
