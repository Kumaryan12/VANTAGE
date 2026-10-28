import math
from datetime import date

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select

from app.api.routes import DB, Browser, owner, snapshot
from app.database.models import ForecastModel, ResearchExperiment
from app.ml.contracts import (
    Comparison,
    ExperimentCompareRequest,
    ExperimentComparison,
    ExperimentDetail,
    Explanation,
    Forecast,
    GovernanceRequest,
    JobSummary,
    MarkdownReport,
    ModelDetail,
    RegimeResponse,
    ResearchRequest,
    ResearchSeriesPoint,
)
from app.ml.report import render_report
from app.ml.service import (
    download_model,
    experiment_comparison,
    experiment_detail,
    explain,
    forecasts_for,
    job_summary,
    model_detail,
    owned_experiment,
    owned_model,
    queue,
    reproduce,
    set_governance,
)

router = APIRouter(prefix="/api/v1/ml", tags=["Quantitative research"])


@router.post("/train", response_model=JobSummary, status_code=202)
@router.post("/backtest", response_model=JobSummary, status_code=202)
def train(body: ResearchRequest, session: Browser, db: DB):
    return queue.submit(db, snapshot(body.mode, session), owner(session), body)


@router.get("/jobs/{experiment_id}", response_model=JobSummary)
def job(experiment_id: str, session: Browser, db: DB):
    return job_summary(owned_experiment(db, experiment_id, owner(session)))


@router.get("/experiments", response_model=list[JobSummary])
def experiments(
    session: Browser, db: DB, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
):
    rows = db.scalars(
        select(ResearchExperiment)
        .where(ResearchExperiment.owner == owner(session))
        .order_by(ResearchExperiment.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [job_summary(owned_experiment(db, row.id, owner(session))) for row in rows]


@router.get("/experiments/{experiment_id}", response_model=ExperimentDetail)
def experiment(experiment_id: str, session: Browser, db: DB):
    return experiment_detail(db, owned_experiment(db, experiment_id, owner(session)))


@router.post("/experiments/{experiment_id}/reproduce", response_model=JobSummary, status_code=202)
def reproduction(experiment_id: str, session: Browser, db: DB):
    return reproduce(db, owned_experiment(db, experiment_id, owner(session)), owner(session))


@router.get("/models", response_model=list[ModelDetail])
def models(session: Browser, db: DB, experiment_id: str):
    owned_experiment(db, experiment_id, owner(session))
    return [
        model_detail(db, row)
        for row in db.scalars(
            select(ForecastModel).where(
                ForecastModel.experiment_id == experiment_id, ForecastModel.owner == owner(session)
            )
        ).all()
    ]


@router.get("/models/{model_id}", response_model=ModelDetail)
def model(model_id: str, session: Browser, db: DB):
    return model_detail(db, owned_model(db, model_id, owner(session)))


@router.get("/models/{model_id}/forecasts", response_model=list[Forecast])
def forecasts(
    model_id: str, session: Browser, db: DB, start: date | None = None, end: date | None = None
):
    return forecasts_for(db, owned_model(db, model_id, owner(session)), start, end)


@router.get("/models/{model_id}/metrics", response_model=Comparison)
def metrics(
    model_id: str, session: Browser, db: DB, start: date | None = None, end: date | None = None
):
    row = owned_model(db, model_id, owner(session))
    return experiment_comparison(
        db, owned_experiment(db, row.experiment_id, owner(session)), start, end
    )


@router.get("/models/{model_id}/explain", response_model=Explanation)
def explanation(model_id: str, session: Browser, db: DB, target: date | None = None):
    return explain(db, owned_model(db, model_id, owner(session)), target)


@router.get("/models/{model_id}/artifact")
def artifact(model_id: str, session: Browser, db: DB):
    return Response(
        download_model(owned_model(db, model_id, owner(session))),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="vantage-model-{model_id}.zip"'},
    )


@router.post("/models/{model_id}/governance", response_model=ModelDetail)
def governance(model_id: str, body: GovernanceRequest, session: Browser, db: DB):
    model = owned_model(db, model_id, owner(session))
    if body.role == "champion":
        from app.governance.authorization import require_champion_review

        require_champion_review(db, session, model)
    return set_governance(db, model, owner(session), body)


@router.get("/comparison", response_model=Comparison)
@router.get("/var-backtests", response_model=Comparison)
def comparison(
    session: Browser, db: DB, experiment_id: str, start: date | None = None, end: date | None = None
):
    return experiment_comparison(
        db, owned_experiment(db, experiment_id, owner(session)), start, end
    )


@router.get("/regimes", response_model=RegimeResponse)
def regimes(session: Browser, db: DB, experiment_id: str):
    exp = owned_experiment(db, experiment_id, owner(session))
    if not exp.summary:
        from app.core.errors import AppError

        raise AppError(
            "RESEARCH_NOT_READY", "Regime evaluation is not available until the job completes.", 409
        )
    return exp.summary["regimes"]


@router.get("/experiments/{experiment_id}/series", response_model=list[ResearchSeriesPoint])
def series(
    experiment_id: str, session: Browser, db: DB, start: date | None = None, end: date | None = None
):
    owned_experiment(db, experiment_id, owner(session))
    rows = {}
    model_rows = db.scalars(
        select(ForecastModel).where(
            ForecastModel.experiment_id == experiment_id, ForecastModel.owner == owner(session)
        )
    ).all()
    for model in model_rows:
        losses = []
        for point in forecasts_for(db, model, start, end):
            row = rows.setdefault(
                point["target_end"],
                {
                    "date": point["target_end"],
                    "origin": point["origin"],
                    "realized_volatility_proxy": abs(point["actual_return"]),
                    "realized_loss": point["realized_loss"],
                    "regime": point["regime"],
                },
            )
            h = point["forecast_variance"]
            losses.append(
                math.log(h) + point["realized_variance_proxy"] / h if h is not None else None
            )
            window = losses[-20:]
            row[f"qlike20_{model.kind}"] = (
                sum(window) / 20
                if len(window) == 20 and all(v is not None for v in window)
                else None
            )
            row[model.kind] = point["forecast_volatility"]
            for field in ("var95", "var99", "exception95", "exception99"):
                row[f"{field}_{model.kind}"] = point[field]
    return [rows[key] for key in sorted(rows)]


@router.get("/experiments/{experiment_id}/report", response_model=MarkdownReport)
def report(experiment_id: str, session: Browser, db: DB):
    exp = owned_experiment(db, experiment_id, owner(session))
    detail = experiment_detail(db, exp)
    rows = db.scalars(select(ForecastModel).where(ForecastModel.experiment_id == exp.id)).all()
    return {
        "markdown": render_report(
            detail,
            [model_detail(db, m) for m in rows],
            exp.summary["regimes"] if exp.summary else {},
        )
    }


@router.post("/experiments/compare", response_model=ExperimentComparison)
def compare_experiments(body: ExperimentCompareRequest, session: Browser, db: DB):
    from app.core.errors import AppError

    if len(set(body.experiment_ids)) != len(body.experiment_ids):
        raise AppError("DUPLICATE_EXPERIMENT", "Choose distinct experiment IDs.")
    rows = [owned_experiment(db, ident, owner(session)) for ident in body.experiment_ids]
    keys = {(e.dataset_hash, e.protocol["test_start"], e.protocol["test_end"]) for e in rows}
    if len(keys) != 1 or any(e.status not in ("completed", "partial") for e in rows):
        raise AppError(
            "INCOMPARABLE_EXPERIMENTS",
            "Compare completed experiments using the same versioned dataset and test dates; configurations can be inspected individually for other datasets.",
        )
    details = [experiment_detail(db, e) for e in rows]
    if len({tuple(str(d) for d in detail.comparison.excluded_dates) for detail in details}) != 1:
        raise AppError(
            "INCOMPARABLE_EXCLUSIONS",
            "Experiments have different valid-date subsets; inspect them individually rather than rank mismatched metrics.",
        )
    return ExperimentComparison(
        experiments=details,
        warnings=[
            "Dataset and evaluation dates match. Review configurations, exclusions, uncertainty and coverage jointly; no automatic champion is assigned."
        ],
    )
