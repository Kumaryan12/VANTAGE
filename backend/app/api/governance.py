from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.api.routes import DB, Browser, owner
from app.auth.contracts import ReviewerSelection
from app.auth.identity import roles_for
from app.database.models import (
    ForecastModel,
    GovernanceModel,
    GovernanceReviewEvent,
    ReviewAssignment,
)
from app.governance.authorization import assign, authorized, public_detail, review_permission
from app.governance.contracts import RegisterModel, ReviewEvent, ReviewModel, ReviewRequest
from app.governance.service import owned, register, review

router = APIRouter(prefix="/api/v1/governance", tags=["Research model governance"])


@router.post("/models", response_model=ReviewModel, status_code=201)
def register_model(body: RegisterModel, session: Browser, db: DB):
    return public_detail(db, register(db, owner(session), body), session, owner(session))


@router.get("/models", response_model=list[ReviewModel])
def models(session: Browser, db: DB, limit: int = Query(30, ge=1, le=100)):
    assigned = select(ReviewAssignment.model_id).where(
        ReviewAssignment.reviewer_id == (session.user_id or ""), ReviewAssignment.active == 1
    )
    include_assignments = bool(
        session.user_id and "RESEARCH_REVIEWER" in roles_for(db, session.user_id)
    )
    rows = db.scalars(
        select(GovernanceModel)
        .where(
            or_(GovernanceModel.owner == owner(session), GovernanceModel.id.in_(assigned))
            if include_assignments
            else GovernanceModel.owner == owner(session)
        )
        .order_by(GovernanceModel.created_at.desc())
        .limit(limit)
    ).all()
    return [public_detail(db, row, session, owner(session)) for row in rows]


@router.get("/models/{ident}", response_model=ReviewModel)
def model(ident: str, session: Browser, db: DB):
    return public_detail(
        db, authorized(db, ident, session, owner(session)), session, owner(session)
    )


@router.post("/models/{ident}/review", response_model=ReviewModel)
def review_model(ident: str, body: ReviewRequest, session: Browser, db: DB):
    row = authorized(db, ident, session, owner(session))
    review_permission(db, session, row, body.status, owner(session))
    review(db, row, body, actor=session)
    return public_detail(db, row, session, owner(session))


@router.get("/events", response_model=list[ReviewEvent])
def events(
    session: Browser, db: DB, model_id: str | None = None, limit: int = Query(100, ge=1, le=200)
):
    if model_id:
        row = authorized(db, model_id, session, owner(session))
    query = select(GovernanceReviewEvent).where(
        GovernanceReviewEvent.owner == (row.owner if model_id else owner(session))
    )
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


@router.post("/models/{ident}/assign")
def assign_reviewer(ident: str, body: ReviewerSelection, session: Browser, db: DB):
    row = owned(db, ident, owner(session))
    return assign(db, row, session, owner(session), body.reviewer_id, body.active)


@router.get("/models/{ident}/evidence")
def review_evidence(ident: str, session: Browser, db: DB):
    row = authorized(db, ident, session, owner(session))
    if row.source_type == "optimization":
        from app.optimization.service import owned as owned_optimization

        source = owned_optimization(db, row.source_id, row.owner)
        return {
            "source_type": row.source_type,
            "source_id": row.source_id,
            "parameters": source.parameters,
            "evidence": source.result,
            "input_hash": source.input_hash,
            "runtime": source.runtime,
        }
    from app.ml.service import owned_experiment, owned_model

    model = owned_model(db, row.source_id, row.owner)
    experiment = owned_experiment(db, model.experiment_id, row.owner)
    return {
        "source_type": row.source_type,
        "source_id": row.source_id,
        "model": model.payload,
        "protocol": experiment.protocol,
        "runtime": experiment.runtime,
        "summary": experiment.summary,
    }
