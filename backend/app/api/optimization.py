from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.routes import DB, Browser, owner, snapshot
from app.core.errors import AppError
from app.database.models import OptimizationCounterfactual, OptimizationRun
from app.optimization.contracts import (
    CounterfactualRequest,
    FrontierRequest,
    OptimizationCompareRequest,
    OptimizationDetail,
    OptimizationJob,
    OptimizationRequest,
    SensitivityRequest,
)
from app.optimization.counterfactual import (
    counterfactual,
    reproduce_counterfactual,
    verified_counterfactual,
)
from app.optimization.service import detail, job, owned, queue, reproduce

router = APIRouter(prefix="/api/v1/optimization", tags=["Portfolio decision laboratory"])


@router.post("/run", response_model=OptimizationJob, status_code=202)
def run(body: OptimizationRequest, session: Browser, db: DB):
    return queue.submit(db, snapshot(body.mode, session), owner(session), body)


@router.post("/feasibility", response_model=OptimizationJob, status_code=202)
def feasibility(body: OptimizationRequest, session: Browser, db: DB):
    return queue.submit(db, snapshot(body.mode, session), owner(session), body)


@router.get("/runs", response_model=list[OptimizationJob])
def runs(
    session: Browser, db: DB, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
):
    rows = db.scalars(
        select(OptimizationRun)
        .where(OptimizationRun.owner == owner(session))
        .order_by(OptimizationRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [job(owned(db, r.id, owner(session))) for r in rows]


@router.get("/runs/{ident}", response_model=OptimizationDetail)
def saved(ident: str, session: Browser, db: DB):
    return detail(owned(db, ident, owner(session)))


@router.post("/runs/{ident}/reproduce", response_model=OptimizationJob, status_code=202)
def reproduction(ident: str, session: Browser, db: DB):
    return reproduce(db, owned(db, ident, owner(session)), owner(session))


@router.get("/constraints")
def constraints(session: Browser):
    from app.optimization.contracts import AllocationConstraints, CostAssumptions

    return {
        "schema": AllocationConstraints.model_json_schema(),
        "defaults": AllocationConstraints().model_dump(),
        "costs": CostAssumptions().model_dump(),
        "sleeve": "Held INR equity sleeve; unavailable cash is not assumed zero.",
        "turnover": "0.5 times gross absolute allocation changes",
        "no_execution": True,
    }


@router.post("/frontier", response_model=OptimizationJob, status_code=202)
def frontier(body: FrontierRequest, session: Browser, db: DB):
    return queue.submit(
        db, snapshot(body.base.mode, session), owner(session), body, kind="frontier"
    )


@router.post("/sensitivity", response_model=OptimizationJob, status_code=202)
def sensitivity(body: SensitivityRequest, session: Browser, db: DB):
    return queue.submit(
        db, snapshot(body.base.mode, session), owner(session), body, kind="sensitivity"
    )


@router.post("/counterfactual")
def stress_comparison(body: CounterfactualRequest, session: Browser, db: DB):
    return counterfactual(
        db, owned(db, body.run_id, owner(session)), owner(session), body.point_index, body.scenario
    )


@router.post("/compare")
def compare(body: OptimizationCompareRequest, session: Browser, db: DB):
    if len(set(body.run_ids)) != len(body.run_ids):
        raise AppError("DUPLICATE_OPTIMIZATION", "Choose distinct optimization runs.")
    rows = [owned(db, ident, owner(session)) for ident in body.run_ids]
    if any(
        r.result is None or r.kind != "single" or not r.result["points"][0]["solution"]["feasible"]
        for r in rows
    ):
        raise AppError(
            "OPTIMIZATION_COMPARISON",
            "Compare completed feasible single-allocation runs; inspect studies separately.",
        )
    keys = {
        (
            tuple(r.result["points"][0]["dataset"]["current_weights"]),
            tuple(r.result["points"][0]["dataset"]["sectors"]),
            r.result["points"][0]["dataset"]["as_of"],
            r.result["points"][0]["dataset"]["sleeve_notional"],
            r.result["points"][0]["dataset"]["price_value_hash"],
            r.result["points"][0]["dataset"]["covariance_hash"],
            r.parameters["confidence"],
            r.parameters["seed"],
            r.parameters["simulations"],
        )
        for r in rows
    }
    if len(keys) != 1:
        raise AppError(
            "OPTIMIZATION_COMPARISON",
            "Saved runs use different valuation/data/covariance/confidence/simulation bases. Inspect them individually or use a labeled sensitivity study.",
            409,
        )
    baseline = rows[0].result["points"][0]
    return {
        "baseline_id": rows[0].id,
        "policy": "Identical economic data and risk settings; original retrieval timestamps remain recorded.",
        "runs": [
            {
                "id": r.id,
                "parameters": r.parameters,
                "point": r.result["points"][0],
                "annual_volatility_delta": r.result["points"][0]["solution"]["annual_volatility"]
                - baseline["solution"]["annual_volatility"],
            }
            for r in rows
        ],
    }


@router.get("/runs/{ident}/counterfactuals")
def saved_counterfactuals(ident: str, session: Browser, db: DB):
    run = owned(db, ident, owner(session))
    rows = db.scalars(
        select(OptimizationCounterfactual)
        .where(
            OptimizationCounterfactual.run_id == ident,
            OptimizationCounterfactual.owner == owner(session),
        )
        .order_by(OptimizationCounterfactual.created_at.desc())
        .limit(20)
    ).all()
    return [verified_counterfactual(db, r, run, owner(session))[0] for r in rows]


@router.post("/counterfactuals/{ident}/reproduce")
def replay_counterfactual(ident: str, session: Browser, db: DB):
    row = db.get(OptimizationCounterfactual, ident)
    if row is None or row.owner != owner(session):
        raise AppError("COUNTERFACTUAL_NOT_FOUND", "Counterfactual not found in this session.", 404)
    run = owned(db, row.run_id, owner(session))
    return reproduce_counterfactual(db, row, run, owner(session))
