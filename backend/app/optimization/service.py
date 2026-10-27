import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib.metadata import version
from threading import BoundedSemaphore
from uuid import uuid4

import numpy as np
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.database.models import OptimizationRun, PortfolioSnapshot, RiskInputArtifact
from app.ml.artifacts import runtime_versions
from app.portfolios.schemas import Portfolio
from app.risk.artifacts import digest, persist_inputs

from .comparison import compare_allocations, risk_metrics
from .contracts import VERSION, OptimizationDetail, OptimizationJob
from .data import capture, prepare
from .solver import solve_allocation
from .studies import point_plan, request_for

RUNNER_ID = str(uuid4())


def runtime():
    return {
        **runtime_versions(),
        "cvxpy": version("cvxpy"),
        "clarabel": version("clarabel"),
        "optimization_version": VERSION,
    }


def job(row):
    return OptimizationJob(
        id=row.id,
        kind=row.kind,
        status=row.status,
        stage=row.stage,
        progress=row.progress,
        synthetic=row.dataset["synthetic"],
        created_at=row.created_at,
        finished_at=row.finished_at,
        solver_status=(
            row.result["points"][0]["solution"]["status"]
            if len({p["solution"]["status"] for p in row.result["points"]}) == 1
            else "mixed"
        )
        if row.result and row.result.get("points")
        else None,
        error=row.error,
        reproduction_of=row.reproduction_of,
    )


def owned(db, ident, owner):
    row = db.get(OptimizationRun, ident)
    if row is None or row.owner != owner:
        raise AppError("OPTIMIZATION_NOT_FOUND", "Optimization run not found in this session.", 404)
    if row.status in ("queued", "running") and row.runner_id != RUNNER_ID:
        row.status = "interrupted"
        row.stage = "Original optimization worker unavailable"
        row.finished_at = datetime.now(UTC)
        row.error = {
            "code": "OPTIMIZATION_INTERRUPTED",
            "message": "Worker restarted; no completed result is claimed. Reproduce the saved request to retry.",
        }
        db.commit()
    if row.result is not None and digest(row.result) != row.result_hash:
        raise AppError(
            "OPTIMIZATION_RESULT_INTEGRITY",
            "Saved optimization result failed its content hash.",
            409,
        )
    return row


def detail(row):
    return OptimizationDetail(
        **job(row).model_dump(),
        version=row.runtime["optimization_version"],
        snapshot_id=row.snapshot_id,
        artifact_id=row.artifact_id,
        input_hash=row.input_hash,
        parameters=row.parameters,
        dataset=row.dataset,
        runtime=row.runtime,
        result=row.result,
    )


def verify_inputs(db, row, owner):
    snapshot = db.get(PortfolioSnapshot, row.snapshot_id)
    artifact = db.get(RiskInputArtifact, row.artifact_id)
    if snapshot is None or artifact is None or snapshot.owner != owner or artifact.owner != owner:
        raise AppError(
            "OPTIMIZATION_INPUT_UNAVAILABLE",
            "Authorized immutable snapshot/history is unavailable.",
            409,
        )
    if (
        digest(snapshot.payload) != snapshot.content_hash
        or digest(artifact.payload) != artifact.content_hash
    ):
        raise AppError(
            "OPTIMIZATION_INPUT_INTEGRITY", "Saved snapshot/history content hash differs.", 409
        )
    expected = digest(
        {
            "snapshot": snapshot.content_hash,
            "artifact": artifact.content_hash,
            "parameters": row.parameters,
            "kind": row.kind,
            "version": VERSION,
        }
    )
    if expected != row.input_hash:
        raise AppError(
            "OPTIMIZATION_INPUT_INTEGRITY",
            "Saved optimization parameters failed their input hash.",
            409,
        )
    if row.result:
        for point in row.result["points"]:
            if point.get("covariance") is not None:
                expected = digest(
                    {
                        "instruments": row.dataset["instruments"],
                        "matrix": point["covariance"],
                        "window": point["parameters"]["window"],
                        "shrinkage": point["parameters"]["shrinkage"],
                    }
                )
                if expected != point["dataset"]["covariance_hash"]:
                    raise AppError(
                        "OPTIMIZATION_COVARIANCE_INTEGRITY",
                        "Saved covariance hash differs from its matrix/asset order.",
                        409,
                    )
    return Portfolio.model_validate(snapshot.payload), artifact.payload


def calculate_point(portfolio, payload, parameters, label="Base allocation", changes=None):
    _, returns, covariance, dataset = prepare(portfolio, payload, parameters)
    current = np.array(dataset["current_weights"])
    result = solve_allocation(
        dataset["instruments"],
        dataset["sectors"],
        current,
        covariance,
        portfolio.total_value,
        parameters,
    )
    current_metrics = risk_metrics(portfolio, current, returns, covariance, parameters)
    comparison = None
    allocations = []
    if result.feasible:
        comparison = compare_allocations(
            portfolio,
            current,
            np.array(result.weights),
            returns,
            covariance,
            parameters,
            current_metrics,
        )
        if abs(comparison["proposed"]["annual_variance"] - result.annual_variance) > 1e-9:
            raise AppError(
                "OPTIMIZATION_RISK_RECONCILIATION",
                "Optimizer and Phase 2 portfolio variance do not reconcile.",
                409,
            )
        for holding, weight in zip(portfolio.holdings, result.weights, strict=True):
            allocations.append(
                {
                    "instrument": holding.instrument,
                    "name": holding.name,
                    "sector": holding.sector,
                    "current_weight": holding.weight,
                    "proposed_weight": weight,
                    "change": weight - holding.weight,
                    "approximate_notional_change": portfolio.total_value
                    * (weight - holding.weight),
                    "frozen": holding.instrument in parameters.constraints.frozen,
                }
            )
    return {
        "label": label,
        "changes": changes or {},
        "parameters": parameters.model_dump(mode="json"),
        "dataset": dataset,
        "covariance": covariance.tolist(),
        "solution": result.model_dump(mode="json"),
        "current_metrics": current_metrics,
        "comparison": comparison,
        "allocations": allocations,
    }


def reproduction_matches(old, new):
    if len(old["points"]) != len(new["points"]):
        return False
    for a, b in zip(old["points"], new["points"], strict=True):
        x, y = a["solution"], b["solution"]
        if x["status"] != y["status"] or x["feasible"] != y["feasible"]:
            return False
        if x["weights"] is not None:
            if not np.allclose(x["weights"], y["weights"], rtol=1e-6, atol=1e-7):
                return False
            if not np.isclose(x["annual_variance"], y["annual_variance"], rtol=1e-7, atol=1e-10):
                return False
            for side in ("current", "proposed"):
                for key in (
                    "annual_volatility",
                    "historical_var",
                    "historical_es",
                    "gaussian_var",
                    "gaussian_es",
                    "monte_carlo_var",
                    "monte_carlo_es",
                ):
                    if not np.isclose(
                        a["comparison"][side][key], b["comparison"][side][key], rtol=1e-6, atol=0.01
                    ):
                        return False
        if a["dataset"]["covariance_hash"] != b["dataset"]["covariance_hash"]:
            return False
    return True


class OptimizationQueue:
    def __init__(self):
        self.capacity = BoundedSemaphore(1)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vantage-optimization")
        self.futures = {}

    def submit(
        self, db, portfolio, owner, parameters, *, kind="single", payload=None, reproduction_of=None
    ):
        if not self.capacity.acquire(blocking=False):
            raise AppError(
                "OPTIMIZATION_BUSY",
                "One bounded optimization job is active; retry after it completes.",
                503,
            )
        try:
            base = parameters if kind == "single" else parameters.base
            payload = payload if payload is not None else capture(db, portfolio, owner, base)
            _, _, _, dataset = prepare(portfolio, payload, base)
            for _, parameters_for_point, _ in point_plan(kind, parameters):
                prepare(portfolio, payload, parameters_for_point)
            snapshot, artifact = persist_inputs(db, portfolio, payload, owner)
            params = parameters.model_dump(mode="json")
            row = OptimizationRun(
                id=str(uuid4()),
                owner=owner,
                kind=kind,
                status="queued",
                stage="Queued for verified equity-sleeve research",
                progress=0,
                runner_id=RUNNER_ID,
                snapshot_id=snapshot.id,
                artifact_id=artifact.id,
                input_hash=digest(
                    {
                        "snapshot": snapshot.content_hash,
                        "artifact": artifact.content_hash,
                        "parameters": params,
                        "kind": kind,
                        "version": VERSION,
                    }
                ),
                parameters=params,
                dataset=dataset,
                runtime=runtime(),
                result=None,
                result_hash=None,
                error=None,
                reproduction_of=reproduction_of,
                created_at=datetime.now(UTC),
                finished_at=None,
            )
            db.add(row)
            db.commit()
            summary = job(row)
            self.futures[row.id] = self.executor.submit(self.execute, db.get_bind(), row.id)
            for key in list(self.futures)[:-64]:
                if self.futures[key].done():
                    self.futures.pop(key, None)
            return summary
        except Exception:
            self.capacity.release()
            raise

    def execute(self, engine, ident):
        try:
            with Session(engine) as db:
                row = db.get(OptimizationRun, ident)
                row.status = "running"
                row.stage = "Rehydrating immutable inputs and solving"
                row.progress = 10
                db.commit()
                portfolio, payload = verify_inputs(db, row, row.owner)
                parameters = request_for(row.kind, row.parameters)
                points = []
                started = time.monotonic()
                planned = point_plan(row.kind, parameters)
                for index, (label, settings, changes) in enumerate(planned):
                    if time.monotonic() - started > 90:
                        raise AppError(
                            "OPTIMIZATION_TIMEOUT",
                            "The bounded study exceeded its 90-second budget.",
                            504,
                        )
                    row.stage = f"Solving {label}"
                    row.progress = 10 + int(80 * index / len(planned))
                    db.commit()
                    points.append(calculate_point(portfolio, payload, settings, label, changes))
                if row.kind == "sensitivity":
                    baseline_weights = points[0]["solution"]["weights"]
                    for point in points:
                        weights = point["solution"]["weights"]
                        point["allocation_stability"] = {
                            "one_way_distance_from_base": float(
                                0.5 * np.abs(np.array(weights) - np.array(baseline_weights)).sum()
                            )
                            if weights is not None and baseline_weights is not None
                            else None,
                            "interpretation": "Allocation distance under a labeled input variation; not an uncertainty interval or predictive validation. Large differences may signal estimation instability.",
                        }
                result = {
                    "kind": row.kind,
                    "points": points,
                    "frontier_mode": parameters.mode if row.kind == "frontier" else None,
                    "plot": [
                        {
                            "point_index": i,
                            "label": p["label"],
                            "x": p["parameters"]["constraints"]["max_turnover"]
                            if row.kind == "frontier" and parameters.mode == "risk_turnover"
                            else p["solution"]["expected_annual_return"]
                            if row.kind == "frontier"
                            else i,
                            "annual_volatility": p["solution"]["annual_volatility"],
                            "status": p["solution"]["status"],
                            "feasible": p["solution"]["feasible"],
                        }
                        for i, p in enumerate(points)
                    ],
                    "warnings": [
                        "SYNTHETIC research does not establish real-market investment performance."
                    ]
                    if portfolio.synthetic
                    else [],
                    "reproduction_match": None,
                    "reproduction_tolerances": {
                        "weights_rtol": 1e-6,
                        "weights_atol": 1e-7,
                        "annual_variance_rtol": 1e-7,
                        "annual_variance_atol": 1e-10,
                        "risk_metric_atol_inr": 0.01,
                        "note": "Timings excluded; singular objectives may yield nonunique weights and a diagnosed mismatch.",
                    },
                }
                if row.reproduction_of:
                    old = owned(db, row.reproduction_of, row.owner)
                    if old.result:
                        result["reproduction_match"] = reproduction_matches(old.result, result)
                row.result = result
                row.result_hash = digest(result)
                row.status = (
                    "completed"
                    if all(
                        p["solution"]["status"] in ("optimal", "optimal_inaccurate", "infeasible")
                        for p in points
                    )
                    else "partial"
                )
                row.stage = "Completed with independently checked solver outcome"
                row.progress = 100
                row.finished_at = datetime.now(UTC)
                if row.kind == "single" and points[0]["solution"]["feasible"]:
                    from app.governance.contracts import RegisterModel
                    from app.governance.service import register

                    db.flush()
                    registered = register(
                        db,
                        row.owner,
                        RegisterModel(source_type="optimization", source_id=row.id),
                        commit=False,
                    )
                    row.result = {**result, "governance_model_id": registered.id}
                    row.result_hash = digest(row.result)
                db.commit()
        except Exception as error:
            with Session(engine) as db:
                row = db.get(OptimizationRun, ident)
                row.status = "failed"
                row.stage = "Optimization could not publish a verified result"
                row.finished_at = datetime.now(UTC)
                row.error = {
                    "code": error.code if isinstance(error, AppError) else "OPTIMIZATION_FAILED",
                    "message": error.message
                    if isinstance(error, AppError)
                    else "Bounded optimization failed; no feasible allocation is claimed.",
                }
                db.commit()
        finally:
            self.capacity.release()


queue = OptimizationQueue()


def reproduce(db, row, owner):
    current = runtime()
    for key in ("python", "numpy", "pandas", "cvxpy", "clarabel", "optimization_version"):
        if row.runtime.get(key) != current.get(key):
            raise AppError(
                "OPTIMIZATION_RUNTIME",
                f"Recorded {key} version differs; restore the saved numerical runtime before reproducing.",
                409,
            )
    portfolio, payload = verify_inputs(db, row, owner)
    return queue.submit(
        db,
        portfolio,
        owner,
        request_for(row.kind, row.parameters),
        kind=row.kind,
        payload=payload,
        reproduction_of=row.id,
    )
