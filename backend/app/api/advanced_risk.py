from contextlib import contextmanager
from threading import BoundedSemaphore
from typing import Literal

from fastapi import APIRouter, Query

from app.api.routes import DB, Browser, owner, snapshot
from app.core.errors import AppError
from app.risk.advanced import run_analysis
from app.risk.contracts import (
    AnalysisRequest,
    AnalysisResult,
    CompareRequest,
    ReplayResult,
    RunComparison,
    RunSummary,
    SavedRun,
    ScenarioAvailability,
    StressRequest,
    StressResult,
)
from app.risk.records import compare_runs, get_run, list_runs, replay_run
from app.risk.stress_service import run_stress, scenario_catalog

router = APIRouter(prefix="/api/v1/risk", tags=["Advanced quantitative risk"])
capacity = BoundedSemaphore(1)


@contextmanager
def calculation_slot(db=None):
    if not capacity.acquire(blocking=False):
        raise AppError(
            "RISK_ENGINE_BUSY", "A bounded risk calculation is in progress. Retry shortly.", 503
        )
    try:
        from app.jobs.interactive import calculation_lease

        with calculation_lease(db):
            yield
    finally:
        capacity.release()


@router.post("/analysis", response_model=AnalysisResult, status_code=201)
@router.post("/var", response_model=AnalysisResult, status_code=201)
@router.post("/expected-shortfall", response_model=AnalysisResult, status_code=201)
@router.post("/monte-carlo", response_model=AnalysisResult, status_code=201)
def analysis(body: AnalysisRequest, session: Browser, db: DB):
    with calculation_slot(db):
        return run_analysis(db, snapshot(body.mode, session), owner(session), body)


@router.get("/contributions", response_model=AnalysisResult)
def contributions(
    session: Browser,
    db: DB,
    mode: Literal["demo", "kite"] = "demo",
    dataset_id: str | None = None,
    confidence: float = Query(0.95, ge=0.90, le=0.995),
    window: int = Query(252, ge=60, le=1260),
    shrinkage: float = Query(0, ge=0, le=1),
):
    body = AnalysisRequest(
        mode=mode, dataset_id=dataset_id, confidence=confidence, window=window, shrinkage=shrinkage
    )
    return analysis(body, session, db)


@router.post("/stress-test", response_model=StressResult, status_code=201)
def stress(body: StressRequest, session: Browser, db: DB):
    with calculation_slot(db):
        return run_stress(db, snapshot(body.mode, session), owner(session), body)


@router.get("/scenarios", response_model=list[ScenarioAvailability])
def scenarios(
    session: Browser, db: DB, mode: Literal["demo", "kite"] = "demo", dataset_id: str | None = None
):
    return scenario_catalog(db, snapshot(mode, session), owner(session), dataset_id)


@router.get("/runs", response_model=list[RunSummary])
def runs(
    session: Browser,
    db: DB,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    mode: Literal["demo", "kite"] | None = None,
):
    return list_runs(db, owner(session), limit, offset, mode)


@router.post("/runs/compare", response_model=RunComparison)
def compare(body: CompareRequest, session: Browser, db: DB):
    return compare_runs(db, body.run_ids, owner(session))


@router.get("/runs/{run_id}", response_model=SavedRun)
def run(run_id: str, session: Browser, db: DB):
    return get_run(db, run_id, owner(session))


@router.post("/runs/{run_id}/replay", response_model=ReplayResult)
def replay(run_id: str, session: Browser, db: DB):
    with calculation_slot(db):
        return replay_run(db, run_id, owner(session))
