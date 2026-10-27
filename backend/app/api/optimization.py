from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.routes import DB, Browser, owner, snapshot
from app.database.models import OptimizationRun
from app.optimization.contracts import OptimizationDetail, OptimizationJob, OptimizationRequest
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
