from typing import Literal

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import select

from app.api.routes import DB, Browser, owner, snapshot
from app.core.errors import AppError
from app.database.models import BackgroundJob
from app.jobs import service
from app.jobs.workflows import submit_report, submit_risk
from app.portfolios.schemas import StrictModel
from app.risk.contracts import AnalysisRequest

router = APIRouter(prefix="/api/v1/jobs", tags=["Bounded background jobs"])


class RiskJob(StrictModel):
    parameters: AnalysisRequest
    idempotency_key: str | None = Field(
        None, min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$"
    )


class ReportJob(StrictModel):
    source_type: Literal["risk", "optimization", "investigation"]
    source_id: str = Field(min_length=36, max_length=36)


@router.get("")
def jobs(session: Browser, db: DB, limit: int = Query(30, ge=1, le=100)):
    rows = db.scalars(
        select(BackgroundJob)
        .where(BackgroundJob.owner == owner(session))
        .order_by(BackgroundJob.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "backend": "celery" if service.durable() else "local",
        "jobs": [service.view(row) for row in rows],
        "local_mode": "Original in-process research workflows remain available in development. Durable jobs require dispatcher and Celery workers.",
    }


@router.get("/{ident}")
def job(ident: str, session: Browser, db: DB):
    return service.view(service.owned(db, ident, owner(session)))


@router.post("/{ident}/cancel")
def cancel(ident: str, session: Browser, db: DB):
    return service.view(service.cancel(db, service.owned(db, ident, owner(session))))


@router.post("/{ident}/retry")
def retry(ident: str, session: Browser, db: DB):
    return service.view(service.retry(db, service.owned(db, ident, owner(session))))


@router.post("/risk", status_code=202)
def risk(body: RiskJob, session: Browser, db: DB):
    if not service.durable():
        raise AppError(
            "DURABLE_JOBS_REQUIRED",
            "Configure dispatcher and Celery workers for asynchronous risk jobs.",
            503,
        )
    return service.view(
        submit_risk(
            db,
            snapshot(body.parameters.mode, session),
            owner(session),
            body.parameters,
            idempotency_key=body.idempotency_key,
        )
    )


@router.post("/report", status_code=202)
def report(body: ReportJob, session: Browser, db: DB):
    if not service.durable():
        raise AppError(
            "DURABLE_JOBS_REQUIRED",
            "Configure dispatcher and Celery workers for private report jobs.",
            503,
        )
    return service.view(submit_report(db, owner(session), body.source_type, body.source_id))
