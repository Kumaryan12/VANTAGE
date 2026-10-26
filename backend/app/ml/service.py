import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import BoundedSemaphore
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.database.models import (
    ForecastModel,
    ModelGovernanceEvent,
    PortfolioSnapshot,
    ResearchExperiment,
    ResearchForecast,
    RiskInputArtifact,
)
from app.ml.artifacts import artifact_zip, read_artifact, runtime_versions, writer
from app.ml.contracts import (
    FEATURE_VERSION,
    MODEL_VERSION,
    ExperimentDetail,
    Explanation,
    JobSummary,
    ModelDetail,
    ResearchRequest,
)
from app.ml.dataset import capture_dataset, prepare_dataset
from app.ml.features import apply_imputer
from app.ml.research import KINDS, compare_forecasts, execute_research
from app.portfolios.schemas import Portfolio
from app.risk.artifacts import digest, persist_inputs

RUNNER_ID = str(uuid4())
logger = logging.getLogger("vantage.research")


def job_summary(exp):
    return JobSummary(
        id=exp.id,
        status=exp.status,
        stage=exp.stage,
        progress=exp.progress,
        created_at=exp.created_at,
        finished_at=exp.finished_at,
        error=exp.error,
        dataset_hash=exp.dataset_hash,
        synthetic=exp.data_info["synthetic"],
        reproduction_of=exp.reproduction_of,
    )


def owned_experiment(db, experiment_id, owner):
    exp = db.get(ResearchExperiment, experiment_id)
    if exp is None or exp.owner != owner:
        raise AppError(
            "EXPERIMENT_NOT_FOUND", "Research experiment not found in the authorized session.", 404
        )
    if exp.status in ("queued", "running") and exp.runner_id != RUNNER_ID:
        exp.status = "interrupted"
        exp.stage = "Worker process restarted"
        exp.finished_at = datetime.now(UTC)
        exp.error = {
            "code": "WORKER_INTERRUPTED",
            "message": "The process that owned this job restarted. No completed result is claimed; reproduce to submit again.",
        }
        db.commit()
    return exp


def owned_model(db, model_id, owner):
    model = db.get(ForecastModel, model_id)
    if model is None or model.owner != owner:
        raise AppError(
            "MODEL_NOT_FOUND", "Forecast model not found in the authorized session.", 404
        )
    return model


def forecasts_for(db, model, start=None, end=None):
    exp = db.get(ResearchExperiment, model.experiment_id)
    if (
        (start and str(start) < exp.protocol["test_start"])
        or (end and str(end) > exp.protocol["test_end"])
        or (start and end and start > end)
    ):
        raise AppError(
            "EVALUATION_WINDOW",
            "Select an increasing window within the saved out-of-sample evaluation period.",
        )
    query = select(ResearchForecast).where(ResearchForecast.model_id == model.id)
    if start:
        query = query.where(ResearchForecast.target_date >= start)
    if end:
        query = query.where(ResearchForecast.target_date <= end)
    return [row.payload for row in db.scalars(query.order_by(ResearchForecast.target_date)).all()]


def experiment_comparison(db, exp, start=None, end=None):
    rows = db.scalars(select(ForecastModel).where(ForecastModel.experiment_id == exp.id)).all()
    if not rows:
        raise AppError(
            "RESEARCH_NOT_READY", "Research models are not available until the job completes.", 409
        )
    models = {row.kind: {**row.payload, "id": row.id, "role": row.role} for row in rows}
    points = [point for row in rows for point in forecasts_for(db, row, start, end)]
    if not points:
        raise AppError("EVALUATION_WINDOW", "No forecasts fall in the selected evaluation window.")
    return compare_forecasts(
        points, models, ResearchRequest.model_validate(exp.parameters), exp.id, start, end
    )


def experiment_detail(db, exp):
    summary = exp.summary or {}
    return ExperimentDetail(
        **job_summary(exp).model_dump(),
        parameters=exp.parameters,
        model_version=exp.runtime["model_version"],
        feature_version=exp.runtime["feature_version"],
        dataset=exp.data_info,
        protocol=exp.protocol,
        runtime=exp.runtime,
        comparison=experiment_comparison(db, exp)
        if exp.status in ("completed", "partial")
        else None,
        reproduction_match=summary.get("reproduction_match"),
        warnings=summary.get("warnings", []),
    )


def model_detail(db, model):
    events = db.scalars(
        select(ModelGovernanceEvent)
        .where(ModelGovernanceEvent.model_id == model.id)
        .order_by(ModelGovernanceEvent.created_at)
    ).all()
    return ModelDetail(
        **{k: v for k, v in model.payload.items() if k in ModelDetail.model_fields},
        experiment_id=model.experiment_id,
        role=model.role,
        governance=[event.payload for event in events],
    )


class ResearchQueue:
    def __init__(self):
        self.capacity = BoundedSemaphore(1)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vantage-research")
        self.futures = {}

    def submit(self, db, portfolio, owner, parameters, payload=None, reproduction_of=None):
        if not self.capacity.acquire(blocking=False):
            raise AppError(
                "RESEARCH_BUSY",
                "One bounded research job is already queued or running. Retry after it finishes.",
                503,
            )
        try:
            payload = (
                payload
                if payload is not None
                else capture_dataset(db, portfolio, owner, parameters)
            )
            _, _, info, protocol = prepare_dataset(portfolio, payload, parameters)
            snapshot, artifact = persist_inputs(db, portfolio, payload, owner)
            runtime = {
                **runtime_versions(),
                "model_version": MODEL_VERSION,
                "feature_version": FEATURE_VERSION,
            }
            input_hash = digest(
                {
                    "snapshot": snapshot.content_hash,
                    "artifact": artifact.content_hash,
                    "parameters": parameters.model_dump(mode="json"),
                    "version": MODEL_VERSION,
                }
            )
            exp = ResearchExperiment(
                id=str(uuid4()),
                owner=owner,
                status="queued",
                stage="Queued for controlled research worker",
                progress=0,
                runner_id=RUNNER_ID,
                snapshot_id=snapshot.id,
                input_artifact_id=artifact.id,
                dataset_hash=info["data_version"],
                input_hash=input_hash,
                parameters=parameters.model_dump(mode="json"),
                data_info=info,
                protocol=protocol,
                runtime=runtime,
                summary=None,
                error=None,
                reproduction_of=reproduction_of,
                created_at=datetime.now(UTC),
                started_at=None,
                finished_at=None,
            )
            db.add(exp)
            db.commit()
            response = job_summary(exp)
            engine = db.get_bind()
            self.futures[exp.id] = self.executor.submit(self._execute, engine, exp.id)
            for key in list(self.futures)[:-64]:
                if self.futures[key].done():
                    self.futures.pop(key, None)
            return response
        except Exception:
            self.capacity.release()
            raise

    def _execute(self, engine, experiment_id):
        try:
            with Session(engine) as db:
                exp = db.get(ResearchExperiment, experiment_id)
                exp.status = "running"
                exp.started_at = datetime.now(UTC)
                exp.stage = "Preparing saved immutable inputs"
                exp.progress = 5
                db.commit()
                snapshot = db.get(PortfolioSnapshot, exp.snapshot_id)
                artifact = db.get(RiskInputArtifact, exp.input_artifact_id)
                if (
                    digest(snapshot.payload) != snapshot.content_hash
                    or digest(artifact.payload) != artifact.content_hash
                ):
                    raise AppError(
                        "RESEARCH_INTEGRITY",
                        "Saved research inputs failed their content-hash check.",
                        409,
                    )
                expected = digest(
                    {
                        "snapshot": snapshot.content_hash,
                        "artifact": artifact.content_hash,
                        "parameters": exp.parameters,
                        "version": MODEL_VERSION,
                    }
                )
                if expected != exp.input_hash:
                    raise AppError(
                        "RESEARCH_INTEGRITY", "Research parameters failed their input hash.", 409
                    )

                def progress(percent, stage):
                    exp.progress = min(95, percent)
                    exp.stage = stage
                    db.commit()

                ids = {kind: str(uuid4()) for kind in KINDS}
                result = execute_research(
                    Portfolio.model_validate(snapshot.payload),
                    artifact.payload,
                    ResearchRequest.model_validate(exp.parameters),
                    ids,
                    writer(experiment_id),
                    progress,
                    experiment_id,
                )
                for kind in KINDS:
                    model = result["models"][kind]
                    db.add(
                        ForecastModel(
                            id=ids[kind],
                            owner=exp.owner,
                            experiment_id=exp.id,
                            kind=kind,
                            role=model["role"],
                            payload={k: v for k, v in model.items() if k != "role"},
                        )
                    )
                db.flush()
                for point in result["forecasts"]:
                    db.add(
                        ResearchForecast(
                            id=str(uuid4()),
                            model_id=point["model_id"],
                            target_date=date.fromisoformat(point["target_end"]),
                            payload=point,
                        )
                    )
                reproduction_match = None
                if exp.reproduction_of:
                    old = db.get(ResearchExperiment, exp.reproduction_of)
                    old_models = db.scalars(
                        select(ForecastModel).where(ForecastModel.experiment_id == old.id)
                    ).all()
                    old_points = sorted(
                        [p for model in old_models for p in forecasts_for(db, model)],
                        key=lambda p: (p["model_kind"], p["target_end"]),
                    )
                    new_points = sorted(
                        result["forecasts"], key=lambda p: (p["model_kind"], p["target_end"])
                    )
                    a = np.array(
                        [
                            p["forecast_variance"] if p["forecast_variance"] is not None else np.nan
                            for p in old_points
                        ]
                    )
                    b = np.array(
                        [
                            p["forecast_variance"] if p["forecast_variance"] is not None else np.nan
                            for p in new_points
                        ]
                    )
                    reproduction_match = len(a) == len(b) and bool(
                        np.allclose(a, b, rtol=1e-8, atol=1e-14, equal_nan=True)
                    )
                exp.summary = {
                    "comparison": result["comparison"],
                    "regimes": result["regimes"],
                    "warnings": result["warnings"],
                    "reproduction_match": reproduction_match,
                }
                exp.status = (
                    "completed"
                    if all(m["status"] == "completed" for m in result["models"].values())
                    else "partial"
                )
                exp.progress = 100
                exp.stage = "Completed with matched out-of-sample evidence"
                exp.finished_at = datetime.now(UTC)
                db.commit()
        except Exception as error:
            logger.error(
                json.dumps(
                    {
                        "event": "research_job_failed",
                        "experiment_id": experiment_id,
                        "error_type": type(error).__name__,
                    }
                )
            )
            with Session(engine) as db:
                exp = db.get(ResearchExperiment, experiment_id)
                if exp is not None:
                    exp.status = "failed"
                    exp.finished_at = datetime.now(UTC)
                    exp.error = {
                        "code": error.code if isinstance(error, AppError) else "RESEARCH_FAILED",
                        "message": error.message
                        if isinstance(error, AppError)
                        else f"Research failed during {exp.stage} ({type(error).__name__}); no completed results are claimed.",
                    }
                    db.commit()
        finally:
            self.capacity.release()


queue = ResearchQueue()


def reproduce(db, exp, owner):
    if (
        exp.runtime["model_version"] != MODEL_VERSION
        or exp.runtime["feature_version"] != FEATURE_VERSION
    ):
        raise AppError(
            "RESEARCH_VERSION", "Saved research methodology is not supported by this runtime.", 409
        )
    snapshot = db.get(PortfolioSnapshot, exp.snapshot_id)
    artifact = db.get(RiskInputArtifact, exp.input_artifact_id)
    if (
        snapshot.owner != owner
        or artifact.owner != owner
        or digest(snapshot.payload) != snapshot.content_hash
        or digest(artifact.payload) != artifact.content_hash
    ):
        raise AppError(
            "RESEARCH_INTEGRITY",
            "Saved research snapshot or input artifact failed validation.",
            409,
        )
    expected = digest(
        {
            "snapshot": snapshot.content_hash,
            "artifact": artifact.content_hash,
            "parameters": exp.parameters,
            "version": MODEL_VERSION,
        }
    )
    if expected != exp.input_hash:
        raise AppError("RESEARCH_INTEGRITY", "Saved research parameters were modified.", 409)
    return queue.submit(
        db,
        Portfolio.model_validate(snapshot.payload),
        owner,
        ResearchRequest.model_validate(exp.parameters),
        artifact.payload,
        exp.id,
    )


def explain(db, model, target=None):
    if model.kind != "lightgbm":
        raise AppError(
            "EXPLANATION_MODEL", "Tree contributions apply only to a saved LightGBM model."
        )
    points = forecasts_for(db, model)
    point = (
        next((p for p in points if p["target_end"] == str(target)), None)
        if target
        else points[-1]
        if points
        else None
    )
    if point is None:
        raise AppError(
            "FORECAST_NOT_FOUND", "No saved out-of-sample prediction exists for that target.", 404
        )
    fit = next(f for f in model.payload["refits"] if f["id"] == point["training_window_id"])
    import lightgbm as lgb

    booster = lgb.Booster(model_str=read_artifact(fit["artifact"]).decode())
    values = apply_imputer(pd.DataFrame([point["feature_values"]]), fit["imputer"])
    raw = float(booster.predict(values, num_threads=1)[0]) / 10000
    contributions = booster.predict(values, pred_contrib=True, num_threads=1)[0] / 10000
    exp = db.get(ResearchExperiment, model.experiment_id)
    floor = exp.parameters["variance_floor"]
    h = max(raw, floor)
    if not math.isclose(h, point["forecast_variance"], rel_tol=1e-10, abs_tol=1e-14):
        raise AppError(
            "PREDICTION_REPRODUCTION",
            "Saved model/feature values do not reproduce the recorded prediction.",
            409,
        )
    names = booster.feature_name()
    rows = []
    sensitivity = []
    for i, name in enumerate(names):
        rows.append(
            {
                "feature": name,
                "observed_value": point["feature_values"].get(name),
                "model_input": float(values[0, i]),
                "variance_contribution": float(contributions[i]),
            }
        )
        std = fit["training_feature_statistics"][name]["std"]
        lower = values.copy()
        upper = values.copy()
        lower[0, i] -= std
        upper[0, i] += std
        sensitivity.append(
            {
                "feature": name,
                "training_std": std,
                "lower_variance": max(
                    float(booster.predict(lower, num_threads=1)[0]) / 10000, floor
                ),
                "upper_variance": max(
                    float(booster.predict(upper, num_threads=1)[0]) / 10000, floor
                ),
            }
        )
    return Explanation(
        model_id=model.id,
        origin=point["origin"],
        target=point["target_end"],
        training_window_id=fit["id"],
        base_variance=float(contributions[-1]),
        raw_variance=raw,
        forecast_variance=h,
        floor_adjustment=h - raw,
        reconstruction_residual=float(contributions.sum() - raw),
        features=sorted(rows, key=lambda row: abs(row["variance_contribution"]), reverse=True),
        sensitivity=sensitivity,
        note="LightGBM built-in TreeSHAP contributions to the saved raw squared-return prediction plus its bias; floors are separate. Sensitivity moves one imputed input by one training standard deviation and can create unrealistic combinations. Neither establishes market causation.",
    )


def set_governance(db, model, owner, body):
    exp = owned_experiment(db, model.experiment_id, owner)
    if exp.status not in ("completed", "partial") or model.payload.get("metrics") is None:
        raise AppError(
            "EVALUATION_REQUIRED",
            "A documented completed evaluation is required before a role change.",
        )
    if body.role == "champion" and (
        model.payload["metrics"]["observations"] < 100 or model.payload["status"] != "completed"
    ):
        raise AppError(
            "CHAMPION_EVIDENCE",
            "Champion review requires a complete model and at least 100 common evaluation observations; this minimum does not establish superiority.",
        )
    for file in model.payload["artifact_files"]:
        read_artifact(file)
    now = datetime.now(UTC)
    event = {
        "from": model.role,
        "to": body.role,
        "rationale": body.rationale,
        "acknowledged_limitations": True,
        "evaluation_hash": digest(model.payload["metrics"]),
        "created_at": now.isoformat(),
    }
    if body.role == "champion":
        for other in db.scalars(
            select(ForecastModel).where(
                ForecastModel.experiment_id == exp.id,
                ForecastModel.role == "champion",
                ForecastModel.id != model.id,
            )
        ):
            other.role = "candidate"
            db.add(
                ModelGovernanceEvent(
                    id=str(uuid4()),
                    model_id=other.id,
                    owner=owner,
                    payload={
                        "from": "champion",
                        "to": "candidate",
                        "rationale": f"Superseded by documented review of {model.id}",
                        "created_at": now.isoformat(),
                    },
                    created_at=now,
                )
            )
    model.role = body.role
    db.add(
        ModelGovernanceEvent(
            id=str(uuid4()), model_id=model.id, owner=owner, payload=event, created_at=now
        )
    )
    db.commit()
    return model_detail(db, model)


def download_model(model):
    if not model.payload["artifact_files"]:
        raise AppError("ARTIFACT_UNAVAILABLE", "This model has no successful fitted artifact.", 409)
    return artifact_zip(model.payload["artifact_files"])
