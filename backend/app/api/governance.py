from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.routes import DB, Browser, owner
from app.database.models import ForecastModel, GovernanceModel, GovernanceReviewEvent
from app.governance.contracts import RegisterModel, ReviewEvent, ReviewModel, ReviewRequest
from app.governance.service import detail, owned, register, review

router = APIRouter(prefix="/api/v1/governance", tags=["Research model governance"])


@router.post("/models", response_model=ReviewModel, status_code=201)
def register_model(body: RegisterModel, session: Browser, db: DB):
    return detail(db, register(db, owner(session), body))


@router.get("/models", response_model=list[ReviewModel])
def models(session: Browser, db: DB, limit: int = Query(30, ge=1, le=100)):
    rows = db.scalars(
        select(GovernanceModel)
        .where(GovernanceModel.owner == owner(session))
        .order_by(GovernanceModel.created_at.desc())
        .limit(limit)
    ).all()
    return [detail(db, row) for row in rows]


@router.get("/models/{ident}", response_model=ReviewModel)
def model(ident: str, session: Browser, db: DB):
    return detail(db, owned(db, ident, owner(session)))


@router.post("/models/{ident}/review", response_model=ReviewModel)
def review_model(ident: str, body: ReviewRequest, session: Browser, db: DB):
    return review(db, owned(db, ident, owner(session)), body)


@router.get("/events", response_model=list[ReviewEvent])
def events(
    session: Browser, db: DB, model_id: str | None = None, limit: int = Query(100, ge=1, le=200)
):
    if model_id:
        owned(db, model_id, owner(session))
    query = select(GovernanceReviewEvent).where(GovernanceReviewEvent.owner == owner(session))
    if model_id:
        query = query.where(GovernanceReviewEvent.model_id == model_id)
    return [
        ReviewEvent(id=r.id, model_id=r.model_id, created_at=r.created_at, payload=r.payload)
        for r in db.scalars(
            query.order_by(GovernanceReviewEvent.created_at.desc()).limit(limit)
        ).all()
    ]


@router.get("/sources")
def sources(session: Browser, db: DB):
    rows = db.scalars(
        select(ForecastModel).where(ForecastModel.owner == owner(session)).limit(30)
    ).all()
    return [
        {
            "source_type": "forecast",
            "source_id": r.id,
            "label": f"{r.kind} · experiment {r.experiment_id[:8]} · {r.payload['status']}",
        }
        for r in rows
    ]
